#!/usr/bin/env python3
"""Fail if any workflow interpolates an Actions expression into shell source.

GitHub Actions substitutes `${{ ... }}` into a `run:` block's script *text*
before bash ever parses it. When the expression carries anything an outsider
controls -- an issue title, a branch name, a step output built from a filename
that arrived with a vendored upstream package -- the result is shell injection
in whatever permissions that job holds.

The 2026-09-08 security review found exactly that in aur-bump.yml: a vendored
filename reached `run:` through a step output, and the payload fired on the
gate-failure path, in a job holding contents/pull-requests/statuses write.

The safe form is to bind the value to an environment variable in `env:` and
reference it as a shell variable, which bash treats as data:

    - run: printf '%s\\n' "$TITLE"
      env:
        TITLE: ${{ github.event.issue.title }}

Expressions in `if:`, `env:`, `with:` and `outputs:` are fine -- those are
evaluated by Actions, not spliced into a shell script -- so only `run:` is
checked here.

Usage: scripts/check-workflow-injection.py [workflow.yml ...]
       (default: .github/workflows/*.yml and *.yaml)

Exit status: 0 clean, 1 at least one interpolation found, 2 usage error.
"""

from __future__ import annotations

import glob
import re
import sys

RUN_BLOCK = re.compile(r"^(\s*)-?\s*run:\s*(.*)$")
EXPRESSION = re.compile(r"\$\{\{")


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def scan(path: str) -> list[tuple[int, str]]:
    """Return (line number, text) for every expression inside a run: block."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    findings: list[tuple[int, str]] = []
    in_block = False
    block_indent = 0

    for n, line in enumerate(lines, start=1):
        match = RUN_BLOCK.match(line)
        if match:
            block_indent = indent_of(line)
            rest = match.group(2).strip()
            # `run: |` / `run: >-` open a block; `run: cmd` is a one-liner.
            in_block = rest in ("|", "|-", "|+", ">", ">-", ">+")
            if not in_block and EXPRESSION.search(rest):
                findings.append((n, line.strip()))
            continue

        if in_block:
            if line.strip() and indent_of(line) <= block_indent:
                in_block = False
            elif EXPRESSION.search(line):
                findings.append((n, line.strip()))

    return findings


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        paths = sorted(
            glob.glob(".github/workflows/*.yml") + glob.glob(".github/workflows/*.yaml")
        )
    if not paths:
        print("no workflow files found", file=sys.stderr)
        return 2

    total = 0
    for path in paths:
        for n, text in scan(path):
            print(f"{path}:{n}: expression interpolated into shell: {text}")
            total += 1

    if total:
        print()
        print(f"{total} interpolation(s) found. Bind the value in `env:` and use")
        print('a shell variable instead: printf \'%s\\n\' "$VAR".')
        return 1

    print(f"no Actions expressions inside run: blocks ({len(paths)} workflow(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
