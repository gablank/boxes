#!/usr/bin/env python3
"""Publish AUR candidates, isolate Claude review, and apply a SHA-bound decision.

Every entrypoint executes only trusted main-branch code. Candidate recipes are
Git data: the publisher applies patches to an isolated index, never a checkout.
Claude receives the diff over stdin, with no tools or GitHub credentials.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

GITHUB_ACTIONS_APP_ID = 15368
MAX_PATCH = 16 * 1024 * 1024
MAX_DIFF = 128 * 1024

class ReviewRejected(Exception):
    """A fixed diagnostic safe to print in public CI logs."""


def require(condition, message):
    if not condition:
        raise ReviewRejected(message)


def context(env):
    require(env.get("GITHUB_EVENT_NAME") in ("schedule", "workflow_dispatch"),
            "Only schedule/workflow_dispatch may request a review")
    require(env.get("GITHUB_REF") == "refs/heads/main", "Review requires main")
    require(env.get("GITHUB_SERVER_URL") == "https://github.com", "Unexpected GitHub host")
    repo = env.get("GITHUB_REPOSITORY", "")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo), "Invalid repository")
    require(env.get("GITHUB_WORKFLOW_REF") == f"{repo}/.github/workflows/aur-bump.yml@refs/heads/main",
            "Unexpected workflow source")
    for name in ("PR_NUMBER", "GITHUB_RUN_ID", "PUBLISH_ATTEMPT", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[1-9][0-9]*", env.get(name, "")), f"Invalid {name}")
    require(int(env["PUBLISH_ATTEMPT"]) <= int(env["GITHUB_RUN_ATTEMPT"]),
            "Publisher attempt is in the future")
    for name in ("HEAD_SHA", "GITHUB_SHA"):
        require(re.fullmatch(r"[0-9a-f]{40}", env.get(name, "")), f"Invalid {name}")
    branch = env.get("BUMP_BRANCH", "")
    suffix = f'-{env["GITHUB_RUN_ID"]}-{env["PUBLISH_ATTEMPT"]}'
    require(re.fullmatch(r"aur/bump-[0-9]{4}-[0-9]{2}-[0-9]{2}" + re.escape(suffix), branch),
            "Branch does not belong to this publisher attempt")
    return {
        "repository": repo,
        "pr_number": int(env["PR_NUMBER"]),
        "head_sha": env["HEAD_SHA"],
        "head_branch": branch,
        "source_sha": env["GITHUB_SHA"],
        "run_id": int(env["GITHUB_RUN_ID"]),
        "publish_attempt": int(env["PUBLISH_ATTEMPT"]),
    }


def run_url(ctx):
    return (f'https://github.com/{ctx["repository"]}/actions/runs/'
            f'{ctx["run_id"]}/attempts/{ctx["publish_attempt"]}')


def validate_pr(ctx, pr, statuses):
    require(pr["number"] == ctx["pr_number"] and pr["state"] == "open"
            and pr["merged"] is False and pr["draft"] is False, "PR is not open and ready")
    require(pr["user"]["login"] == "github-actions[bot]" and pr["user"]["type"] == "Bot",
            "PR was not opened by GitHub Actions")
    require(pr["head"]["repo"]["full_name"] == ctx["repository"]
            and pr["base"]["repo"]["full_name"] == ctx["repository"], "Fork or wrong repository")
    require(pr["base"]["ref"] == "main", "Wrong target branch")
    require(pr["head"]["ref"] == ctx["head_branch"]
            and pr["head"]["sha"] == ctx["head_sha"], "Publisher branch or commit changed")
    require("aur-bump" in [label["name"] for label in pr["labels"]], "Missing aur-bump label")
    require("needs-review" not in [label["name"] for label in pr["labels"]], "PR is held for human review")
    # GitHub lists statuses newest first. Never accept an old success after a
    # newer failure, even when the old target URL matches this run.
    status = next((s for s in statuses if s["context"] == "aur-bump/eligible"), None)
    require(status is not None and status["state"] == "success"
            and status["creator"]["login"] == "github-actions[bot]"
            and status["target_url"] == run_url(ctx), "Missing or mismatched publisher status")


def validate_rules(rules):
    require(any(
        check.get("context") == "aur-bump/eligible"
        and check.get("integration_id") == GITHUB_ACTIONS_APP_ID
        for rule in rules if rule.get("type") == "required_status_checks"
        for check in rule.get("parameters", {}).get("required_status_checks", [])
    ), "main must require aur-bump/eligible from the GitHub Actions app")


def git(repo, *args, env=None):
    result = subprocess.run(["git", "-C", str(repo), *args], env=env,
                            capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, "Could not inspect the published Git objects")
    return result.stdout


def build_diff(ctx, repo):
    source, head = ctx["source_sha"], ctx["head_sha"]
    require(git(repo, "rev-parse", "HEAD").strip() == source, "Checkout is not the publisher source")
    require(git(repo, "rev-list", "--parents", "-n", "1", head).split() == [head, source],
            "Candidate must be one commit directly on the publisher source")
    paths = git(repo, "diff", "--name-only", "--no-renames", "-z", source, head, "--").split("\0")[:-1]
    require(paths and all(p == "aur/manifest.tsv" or re.fullmatch(
        r"aur/[a-z0-9][a-z0-9._+-]*/PKGBUILD", p) for p in paths), "Candidate changed disallowed paths")
    # The isolated index makes the existing staged-diff validator inspect the
    # entire candidate without checking out or executing any candidate files.
    with tempfile.TemporaryDirectory(prefix="aur-review-index-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(repo, "read-tree", head, env=env)
        validator = Path(__file__).resolve().with_name("validate-aur-diff.py")
        result = subprocess.run([sys.executable, str(validator), "--repo", str(repo)],
                                env=env, capture_output=True, timeout=60)
        require(result.returncode == 0, "Published changes failed the trusted literal-diff validator")
    patch = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-color",
                "--unified=0", "--inter-hunk-context=0", "--no-function-context",
                "--src-prefix=a/", "--dst-prefix=b/", source, head, "--")
    # Git adds a nearby function/declaration to @@ headers even with -U0.
    # Strip that context too; only changed lines and diff metadata may survive.
    patch = re.sub(r"^(@@ [^\n]*? @@)[^\n]*$", r"\1", patch, flags=re.MULTILINE)
    require(patch and not any(line.startswith(" ") for line in patch.splitlines()),
            "Unexpected unchanged context in review diff")
    return patch


def prepare_diff(ctx):
    git(".", "-c", "core.hooksPath=/dev/null", "fetch", "--no-tags", "--no-write-fetch-head",
        f'https://github.com/{ctx["repository"]}.git', ctx["head_sha"])
    return build_diff(ctx, Path.cwd())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReviewRejected("API redirect refused")


def api(ctx, path, data=None, method=None):
    token = os.environ.get("GH_TOKEN", "")
    require(token, "Missing GitHub token")
    url = f'https://api.github.com/repos/{ctx["repository"]}/{path}'
    req = urllib.request.Request(
        url, data=None if data is None else json.dumps(data).encode(), method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=45) as response:
        body = response.read()
        return json.loads(body) if body else None


def source_context(env):
    # Reuse the full context validation before any job can act on GitHub.
    attempt, run = env.get("GITHUB_RUN_ATTEMPT", ""), env.get("GITHUB_RUN_ID", "")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return context({**env, "PUBLISH_ATTEMPT": attempt, "PR_NUMBER": "1",
                    "HEAD_SHA": env.get("GITHUB_SHA", ""),
                    "BUMP_BRANCH": f"aur/bump-{date}-{run}-{attempt}"})


def bounded_file(path, limit):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Missing or unsafe handoff file")
    with path.open("rb") as source:
        data = source.read(limit + 1)
    require(len(data) <= limit, "Handoff exceeds size limit; human intervention required")
    return data


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def quoted(text, limit=12000):
    # Encode HTML, mentions, fences and terminal controls in human-facing data.
    text = "".join(c if c.isprintable() or c in "\n\t" else f"\\x{ord(c):02x}" for c in text)
    rendered = html.escape(text).replace("@", "&#64;").replace("`", "&#96;")
    if len(rendered) > limit:
        rendered = rendered[:limit] + "\n[Report excerpt truncated; inspect the complete change in Files changed.]"
    return "<pre>" + rendered + "</pre>"


def literal_check(repo, env=None):
    validator = Path(__file__).resolve().with_name("validate-aur-diff.py")
    result = subprocess.run([sys.executable, str(validator), "--repo", str(repo)],
                            env=env, capture_output=True, timeout=60)
    return result.returncode == 0, result.stdout.decode("utf-8", errors="replace")


def bundle(out):
    source_context(os.environ)
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["git", "diff", "--cached", "--binary", "--no-ext-diff",
                           "--no-textconv", "--no-renames", "--", "aur/"],
                          capture_output=True, check=True, timeout=60)
    require(proc.stdout, "No candidate changes")
    require(len(proc.stdout) <= MAX_PATCH, "Candidate patch exceeds publishing limit")
    (out / "bump.patch").write_bytes(proc.stdout)
    provenance = Path(os.environ["RUNNER_TEMP"]) / "provenance.txt"
    report = {
        "vendor_pass": os.environ.get("VENDOR_RESULT") == "success",
        "provenance_pass": os.environ.get("PROVENANCE_VERDICT") == "PASS",
        "provenance_report": provenance.read_text(errors="replace")[:12000] if provenance.is_file()
        else "Provenance check did not complete.",
    }
    (out / "audit.json").write_text(json.dumps(report))


def stage_candidate(repo, patch, env):
    source = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "read-tree", source, env=env)
    proc = subprocess.run(["git", "-C", str(repo), "apply", "--cached", "--binary",
                           "--whitespace=nowarn", "-"], input=patch, capture_output=True,
                          env=env, timeout=60)
    require(proc.returncode == 0, "Candidate patch could not be applied to isolated index")
    paths = git(repo, "diff", "--cached", "--name-only", "--no-renames", "-z", env=env).split("\0")[:-1]
    require(paths and all(p.startswith("aur/") for p in paths), "Candidate escapes aur/")
    # Even an unvalidated draft must never change the trusted publisher's files.
    passed, report = literal_check(repo, env)
    tree = git(repo, "write-tree", env=env).strip()
    return tree, passed, report


def publish(incoming, request=api):
    ctx = source_context(os.environ)
    require(git(".", "rev-parse", "HEAD").strip() == ctx["source_sha"], "Untrusted publisher checkout")
    patch = bounded_file(incoming / "bump.patch", MAX_PATCH)
    audit = strict_json(bounded_file(incoming / "audit.json", 64000))
    require(set(audit) == {"vendor_pass", "provenance_pass", "provenance_report"}
            and type(audit["vendor_pass"]) is bool
            and type(audit["provenance_pass"]) is bool
            and isinstance(audit["provenance_report"], str), "Malformed audit report")
    with tempfile.TemporaryDirectory(prefix="aur-publish-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index"),
               "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
               "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
               "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
        tree, literal, report = stage_candidate(Path.cwd(), patch, env)
        eligible = literal and audit["provenance_pass"] and audit["vendor_pass"]
        head = git(".", "-c", "core.hooksPath=/dev/null", "commit-tree", tree, "-p", ctx["source_sha"],
                   "-m", "aur: update vendored packages", env=env).strip()
    ctx["head_sha"] = head
    git(".", "-c", "core.hooksPath=/dev/null", "push", "origin", f'{head}:refs/heads/{ctx["head_branch"]}')
    request(ctx, f"statuses/{head}", {
        "state": "success" if eligible else "failure", "context": "aur-bump/eligible",
        "target_url": run_url(ctx),
        "description": "Mechanical checks passed" if eligible else "Human review required; mechanical checks failed"})
    body = ("## Automated AUR update\n\n"
            + ("Mechanical checks passed; isolated Claude review follows.\n\n" if eligible else
               "**Human review required. Automatic review and merging are disabled for this candidate.**\n\n")
            + f"Publisher: {run_url(ctx)}\n\nCandidate SHA: `{head}`\n\n"
            + ("Vendoring completed.\n\n" if audit["vendor_pass"] else
               "**Vendoring failed partway through. This is a partial candidate; inspect the audit job.**\n\n")
            + "### Literal-change check\n\n" + quoted(report)
            + "\n\n### Upstream provenance check\n\n"
            + ("PASS\n" if audit["provenance_pass"] else "FAIL\n")
            + quoted(audit["provenance_report"])
            + "\n\nReview the complete patch in **Files changed**. No candidate file was executed or checked out by the publisher.\n")
    pr = request(ctx, "pulls", {"title": "aur: update vendored packages", "head": ctx["head_branch"],
                               "base": "main", "body": body, "draft": not eligible})
    ctx["pr_number"] = pr["number"]
    require(type(ctx["pr_number"]) is int and ctx["pr_number"] > 0, "Invalid created PR")
    labels = ["aur-bump"] + ([] if eligible else ["needs-review"])
    for name in labels:
        try:
            request(ctx, "labels", {"name": name, "color": "0e8a16" if name == "aur-bump" else "d93f0b"})
        except urllib.error.HTTPError as error:
            if error.code != 422:
                raise
            error.close()
    request(ctx, f'issues/{ctx["pr_number"]}/labels', {"labels": labels})
    with open(os.environ["GITHUB_OUTPUT"], "a") as out:
        for key, value in {"pr_number": ctx["pr_number"], "head_sha": head, "branch": ctx["head_branch"],
                           "publish_attempt": ctx["publish_attempt"], "eligible": str(eligible).lower()}.items():
            out.write(f"{key}={value}\n")
    print(f'Opened PR #{ctx["pr_number"]}; automatic review eligible: {eligible}')


def preflight(ctx, request=api):
    pr = request(ctx, f'pulls/{ctx["pr_number"]}')
    statuses = request(ctx, f'commits/{ctx["head_sha"]}/statuses?per_page=100')
    validate_pr(ctx, pr, statuses)
    validate_rules(request(ctx, "rules/branches/main"))


def review_request(ctx, diff=prepare_diff):
    patch = diff(ctx)
    require(len(patch.encode()) <= MAX_DIFF, "Diff too large; human review required")
    prompt = Path(__file__).resolve().parent.parent / ".github/aur-vet-prompt.md"
    return {"target": ctx, "diff": patch, "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest()}


def prepare(out):
    ctx = context(os.environ)
    preflight(ctx)
    out.write_text(json.dumps(review_request(ctx)))


def validate_verdict(value):
    require(isinstance(value, dict) and set(value) == {"verdict", "reason"}, "Invalid review schema")
    require(value["verdict"] in ("PASS", "FAIL") and isinstance(value["reason"], str)
            and 1 <= len(value["reason"]) <= 8000, "Invalid review verdict or explanation")
    return value


def run_claude(request, prompt, token, runner=subprocess.run):
    require(token and "\n" not in token and "\r" not in token, "Missing Claude subscription OAuth secret")
    with tempfile.TemporaryDirectory(prefix="aur-claude-") as tmp:
        cwd = Path(tmp) / "empty"
        cwd.mkdir()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
               "CLAUDE_CODE_OAUTH_TOKEN": token, "CLAUDE_CONFIG_DIR": str(Path(tmp) / "config"),
               "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        command = ["claude", "-p", "--safe-mode", "--tools", "", "--disallowedTools", "*",
                   "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                   "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
                   "--permission-mode", "dontAsk", "--max-turns", "1", "--output-format", "json",
                   "--model", "opus", "--system-prompt", prompt]
        result = runner(command, input=request["diff"], text=True, capture_output=True,
                        cwd=cwd, env=env, timeout=600)
        require(result.returncode == 0, "Claude process failed; inspect authentication and usage limits")
        envelope = strict_json(result.stdout)
        require(envelope.get("type") == "result" and envelope.get("subtype") == "success"
                and envelope.get("is_error") is False, "Claude did not return a successful result")
        return validate_verdict(strict_json(envelope["result"]))


def review(incoming, out):
    source_context(os.environ)
    data = strict_json(bounded_file(incoming, MAX_DIFF + 4000))
    require(set(data) == {"target", "diff", "prompt_sha256"}, "Invalid review request")
    prompt = Path(__file__).resolve().parent.parent / ".github/aur-vet-prompt.md"
    require(hashlib.sha256(prompt.read_bytes()).hexdigest() == data["prompt_sha256"], "Review prompt changed")
    try:
        decision = run_claude(data, prompt.read_text(), os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""))
    except (ReviewRejected, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        decision = {"verdict": "ERROR", "reason": "Claude review failed or returned invalid output. No merge attempted; check the review job and OAuth secret."}
    out.write_text(json.dumps({"request_sha256": digest(data), **decision}))
    # Never print model output, OAuth errors or session details into public logs.
    print("Isolated review completed: " + decision["verdict"])


def finish(result_file, request=api, diff=prepare_diff):
    ctx = context(os.environ)
    preflight(ctx, request)
    decision = {"verdict": "ERROR", "reason": "Review preparation or execution failed. No merge attempted; inspect this workflow run."}
    try:
        data = review_request(ctx, diff)
        record = strict_json(bounded_file(result_file, 40000))
        require(set(record) == {"request_sha256", "verdict", "reason"}
                and record["request_sha256"] == digest(data), "Review does not match this exact change and prompt")
        if record["verdict"] != "ERROR":
            decision = validate_verdict({"verdict": record["verdict"], "reason": record["reason"]})
    except (ReviewRejected, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        pass
    if decision["verdict"] != "PASS":
        request(ctx, f'statuses/{ctx["head_sha"]}', {"state": "failure", "context": "aur-bump/eligible",
                "target_url": run_url(ctx), "description": "Review did not pass; human review required"})
        try:
            request(ctx, "labels", {"name": "needs-review", "color": "d93f0b"})
        except urllib.error.HTTPError as error:
            if error.code != 422:
                raise
            error.close()
        request(ctx, f'issues/{ctx["pr_number"]}/labels', {"labels": ["needs-review"]})
        request(ctx, f'issues/{ctx["pr_number"]}/comments', {
            "body": f'## AUR review: {decision["verdict"]}\n\nReviewed SHA: `{ctx["head_sha"]}`\n\n'
                    + quoted(decision["reason"], 8000) + "\n\nLeft unmerged. Publisher: " + run_url(ctx)})
        print("Left PR unmerged; posted review findings.")
        return
    # Repeat live metadata immediately before the atomic expected-SHA merge.
    preflight(ctx, request)
    result = request(ctx, f'pulls/{ctx["pr_number"]}/merge',
                     {"sha": ctx["head_sha"], "merge_method": "squash"}, method="PUT")
    require(result.get("merged") is True and re.fullmatch(r"[0-9a-f]{40}", result.get("sha", "")),
            "Merge not confirmed; inspect GitHub before any retry")
    print("Merged reviewed commit as " + result["sha"])
    # GITHUB_TOKEN merges do not trigger build.yml's push event.
    request(ctx, "actions/workflows/build.yml/dispatches", {"ref": "main"})
    print("Requested image build on main.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("bundle", "publish", "prepare", "review", "finish"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.phase == "bundle":
            bundle(args.output)
        elif args.phase == "publish":
            publish(args.input)
        elif args.phase == "prepare":
            prepare(args.output)
        elif args.phase == "review":
            review(args.input, args.output)
        else:
            finish(args.input)
    except (ReviewRejected, ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        # Raw subprocess/HTTP bodies may contain credentials or attacker text.
        message = str(error) if isinstance(error, ReviewRejected) else "metadata, transport or configuration error"
        print("AUR workflow stopped: " + message + ". Inspect the run and PR before retrying.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
