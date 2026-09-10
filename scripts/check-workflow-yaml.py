#!/usr/bin/env python3
"""Parse workflow YAML from the worktree, or from the exact commit being pushed.

Requires Mike Farah's yq v4 (Arch: go-yq). YQ or the local Git setting box.yq
can select an existing executable outside PATH. This checks YAML syntax, not
the GitHub Actions schema or expressions.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="validate workflows in this Git commit")
    args = parser.parse_args()

    try:
        if args.ref:
            commit = git("rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}").decode().strip()
            paths = git("ls-tree", "-r", "--name-only", "-z", commit, "--", ".github/workflows").decode().split("\0")
            files = {
                path: git("show", f"{commit}:{path}")
                for path in paths
                if Path(path).parent == Path(".github/workflows")
                and Path(path).suffix in (".yml", ".yaml")
            }
        else:
            files = {
                str(path): path.read_bytes()
                for path in sorted(Path(".github/workflows").glob("*"))
                if path.suffix in (".yml", ".yaml")
            }

        if not files:
            print("No workflow YAML files to validate.")
            return 0

        configured = subprocess.run(["git", "config", "--get", "box.yq"], capture_output=True, text=True)
        yq = os.environ.get("YQ") or configured.stdout.strip() or "yq"
        version = subprocess.run([yq, "--version"], capture_output=True, text=True)
        if version.returncode or "github.com/mikefarah/yq/" not in version.stdout or "version v4." not in version.stdout:
            print("Requires Mike Farah's yq v4 (Arch package: go-yq). Set YQ or git config --local box.yq to an existing binary.", file=sys.stderr)
            return 2

        failed = False
        for path, content in files.items():
            result = subprocess.run([yq, "eval", ".", "-"], input=content, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if result.returncode:
                print(f"{path}: {result.stderr.decode().strip()}", file=sys.stderr)
                failed = True
        if failed:
            return 1
        print(f"Workflow YAML valid ({len(files)} files{', commit ' + commit[:12] if args.ref else ''}).")
        return 0
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Cannot validate workflow YAML: {exc}. Requires git and Mike Farah's yq v4 (go-yq).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
