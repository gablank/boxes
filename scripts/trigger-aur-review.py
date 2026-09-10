#!/usr/bin/env python3
"""Trigger one AUR review from trusted publisher outputs, never PR event text.

Runs only in aur-bump.yml's review job, after audit + publish succeed. The
aur-review environment must restrict its token to the main branch. This script
adds a deterministic metadata gate; the routine must independently repeat it.
No candidate checkout, recipe execution, redirects, or automatic POST retries.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request


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
    # GitHub lists statuses newest first. Never accept an old success after a
    # newer failure, even when the old target URL matches this run.
    status = next((s for s in statuses if s["context"] == "aur-bump/eligible"), None)
    require(status is not None and status["state"] == "success"
            and status["creator"]["login"] == "github-actions[bot]"
            and status["target_url"] == run_url(ctx), "Missing or mismatched publisher status")


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


def trigger(env, request=request_json):
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
    print("Review target: " + json.dumps(ctx, sort_keys=True))
    result = request(f"https://api.anthropic.com/v1/claude_code/routines/{routine_id}/fire", token,
                     {"text": json.dumps(ctx, sort_keys=True)})
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
    except (ValueError, KeyError, TypeError, StopIteration, OSError):
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
