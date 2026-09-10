#!/usr/bin/env python3
"""Trigger one AUR review from trusted publisher outputs, never PR event text.

Runs only in aur-bump.yml's review job, after audit + publish succeed. The
aur-review environment must restrict its token to the main branch. This script
checks eligibility and the required status integration, then sends only a
validated zero-context diff plus fixed identifiers. No candidate checkout,
recipe execution, PR prose, redirects, or automatic POST retries.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

GITHUB_ACTIONS_APP_ID = 15368  # github.com/apps/github-actions (public GitHub only)


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


def request_json(url, token, payload=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if payload is not None:
        headers.update({"Content-Type": "application/json", "anthropic-version": "2023-06-01",
                        "anthropic-beta": "experimental-cc-routine-2026-04-01"})
    req = urllib.request.Request(url, headers=headers,
                                 data=None if payload is None else json.dumps(payload).encode())
    with urllib.request.build_opener(NoRedirect).open(req, timeout=45) as response:
        return json.load(response)


def trigger(env, request=request_json, diff=prepare_diff):
    ctx = context(env)
    routine_id = env.get("AUR_REVIEW_ROUTINE_ID", "")
    require(re.fullmatch(r"trig_[A-Za-z0-9]+", routine_id), "Set AUR_REVIEW_ROUTINE_ID in aur-review")
    token = env.get("AUR_REVIEW_ROUTINE_TOKEN", "")
    require(token and "\n" not in token and "\r" not in token,
            "Set AUR_REVIEW_ROUTINE_TOKEN in aur-review")
    require(env.get("GH_TOKEN"), "Missing GitHub read token")
    api = f'https://api.github.com/repos/{ctx["repository"]}'
    pr = request(f'{api}/pulls/{ctx["pr_number"]}', env["GH_TOKEN"])
    statuses = request(f'{api}/commits/{ctx["head_sha"]}/statuses?per_page=100', env["GH_TOKEN"])
    # If the status is not in the latest 100, fail closed rather than guessing.
    validate_pr(ctx, pr, statuses)
    validate_rules(request(f"{api}/rules/branches/main", env["GH_TOKEN"]))
    payload = {**ctx, "diff": diff(ctx)}
    text = json.dumps(payload, sort_keys=True)
    require(len(text.encode("utf-8")) <= 65536, "Review payload exceeds the API limit; human review required")
    print("Review target: " + json.dumps(ctx, sort_keys=True))
    result = request(f"https://api.anthropic.com/v1/claude_code/routines/{routine_id}/fire", token,
                     {"text": text})
    session_id = result.get("claude_code_session_id", "")
    session_url = result.get("claude_code_session_url", "")
    require(result.get("type") == "routine_fire"
            and re.fullmatch(r"session_[A-Za-z0-9]+", session_id)
            and session_url == f"https://claude.ai/code/{session_id}",
            "Unexpected response; check the routine run list before retrying")
    return session_url


def main():
    try:
        trigger(os.environ)
    except ReviewRejected as error:
        print(f"Review request refused: {error}. Check the routine run list before retrying.",
              file=sys.stderr)
        return 1
    except urllib.error.HTTPError as error:
        # Never print response bodies or request headers (may contain secrets).
        error.close()
        print(f"Review request failed: HTTP {error.code}. Check the routine run list before retrying.",
              file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError, StopIteration, OSError, subprocess.TimeoutExpired):
        print("Review request failed: configuration, metadata, or transport check failed. "
              "No automatic retry; check the routine run list before rerunning the failed job.",
              file=sys.stderr)
        return 1
    # Session links belong to a private Claude account; public Actions logs
    # record acceptance only, not the private conversation's URL or response.
    summary = "Claude accepted the AUR review request. Check the routine run list for its outcome.\n"
    print(summary, end="")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
            output.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
