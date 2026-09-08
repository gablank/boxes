#!/usr/bin/env python3
"""Deterministically validate a vendored AUR bump.

This replaces the old "strip the routine lines and read what's left" filter,
which was unsafe. PKGBUILDs are shell programs, so a line beginning with
`pkgver=` or `sha256sums=` can carry command substitution, a trailing `;` and
another command, or a line continuation. Stripping such lines by prefix told the
reader "nothing but routine version/checksum lines" for a diff that in fact
changed what the build executes.

The rule here is inverted and fails closed: every changed line must match one of
a small set of exact literal shapes, and anything else -- including a line that
merely *looks* routine -- fails the run. A bump that a human should read can
never be reported as routine.

The candidate PKGBUILD is never sourced, executed, or passed to a shell. Only
the diff text is inspected.

Exit status: 0 all changes validated, 1 something needs a human, 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# A literal value: no shell metacharacters at all. This is the whole point of
# the validator, so keep it strict -- $ ` ( ) ; & | < > \ " ' whitespace and
# newline are all absent by construction.
SAFE_VALUE = r"[A-Za-z0-9._+~:-]+"
HEX40 = r"[0-9a-f]{40}"
CHECKSUM = r"[0-9a-f]{32,128}"

# A single checksum array entry. 'SKIP' is accepted by the grammar so that
# replacing a SKIP with a real checksum validates; introducing one is rejected
# separately in check_content, since it disables an integrity check.
CKSUM_VAL = rf"(?:{CHECKSUM}|SKIP)"
QUOTED_CKSUM = rf"(?:'{CKSUM_VAL}'|\"{CKSUM_VAL}\"|{CKSUM_VAL})"
CKSUM_ARRAY = r"(?:sha[0-9]+sums|md5sums|b2sums)(?:_[a-z0-9_]+)?"

# Every line shape a routine bump is permitted to add or remove. Anchored whole
# -- a trailing `; curl ...` cannot match.
ALLOWED_PKGBUILD = [
    re.compile(rf"pkgver={SAFE_VALUE}$"),
    re.compile(rf"pkgver='{SAFE_VALUE}'$"),
    re.compile(rf'pkgver="{SAFE_VALUE}"$'),
    re.compile(rf"_pkgver={SAFE_VALUE}$"),
    re.compile(r"pkgrel=[0-9]+$"),
    re.compile(rf"_commit={HEX40}$"),
    re.compile(rf"_commit='{HEX40}'$"),
    re.compile(rf'_commit="{HEX40}"$'),
    # Checksum arrays, whether written on one line or spread over several, and
    # quoted with ' or " or not at all -- all three occur in the wild.
    re.compile(rf"{CKSUM_ARRAY}=\($"),
    re.compile(rf"{CKSUM_ARRAY}=\({QUOTED_CKSUM}(?:[ \t]+{QUOTED_CKSUM})*\)$"),
    re.compile(rf"{QUOTED_CKSUM}$"),
    re.compile(rf"{QUOTED_CKSUM}\)$"),
    re.compile(r"\)$"),
]

# pkgbase <TAB> commit <TAB> ISO date
ALLOWED_MANIFEST = re.compile(rf"[a-z0-9][a-z0-9._+-]*\t{HEX40}\t[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$")

PKGBUILD_PATH = re.compile(r"aur/[^/]+/PKGBUILD$")
MANIFEST_PATH = "aur/manifest.tsv"

# git's raw format reports these; only an ordinary non-executable file may change.
REGULAR_FILE_MODE = "100644"


def sanitize(text: str) -> str:
    """Render an untrusted line safely for a report.

    The result is only ever written to a file and `cat`-ed, never interpolated
    into a shell command or an Actions expression, but control characters could
    still corrupt a log or smuggle terminal escapes past a reader.
    """
    return "".join(c if c.isprintable() or c == "\t" else f"\\x{ord(c):02x}" for c in text)


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def check_paths_and_modes(repo: str, staged: bool) -> list[str]:
    """Reject anything but an in-place edit of a regular PKGBUILD or manifest.

    Symlinks (120000), submodule links (160000), a newly executable file
    (100755) and type changes all fail here, before any content is read.
    """
    args = ["diff", "--raw", "-z", "--no-renames"]
    if staged:
        args.append("--cached")
    args += ["--", "aur/"]
    raw = git(repo, *args)

    problems: list[str] = []
    fields = raw.split("\0")
    i = 0
    while i < len(fields):
        meta = fields[i]
        if not meta.startswith(":"):
            i += 1
            continue
        # :<old-mode> <new-mode> <old-sha> <new-sha> <status>
        parts = meta[1:].split()
        if len(parts) < 5:
            problems.append(f"unparseable git raw entry: {sanitize(meta)}")
            i += 1
            continue
        old_mode, new_mode, _, _, status = parts[:5]
        path = fields[i + 1] if i + 1 < len(fields) else ""
        i += 2

        shown = sanitize(path)
        if status != "M":
            problems.append(
                f"{shown}: status {status} -- a routine bump only modifies "
                f"existing files (adding or removing a vendored package is a "
                f"manual pull request)"
            )
            continue
        if old_mode != REGULAR_FILE_MODE or new_mode != REGULAR_FILE_MODE:
            problems.append(
                f"{shown}: file mode {old_mode} -> {new_mode}, expected "
                f"{REGULAR_FILE_MODE} (symlink, submodule or executable bit)"
            )
            continue
        if not (PKGBUILD_PATH.fullmatch(path) or path == MANIFEST_PATH):
            problems.append(f"{shown}: not a PKGBUILD or the manifest")
    return problems


def check_content(repo: str, staged: bool) -> list[str]:
    """Every added and removed line must match an allowed literal shape.

    Removed lines are checked too: deleting a checksum entry or a chunk of a
    build function changes behaviour just as much as adding one.
    """
    args = ["diff", "-U0", "--no-ext-diff", "--no-textconv", "--no-renames"]
    if staged:
        args.append("--cached")
    args += ["--", "aur/"]
    patch = git(repo, *args)

    problems: list[str] = []
    current = ""
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if line.startswith(("--- ", "+++ ", "@@", "diff --git", "index ", "old mode", "new mode")):
            continue
        if not line or line[0] not in "+-":
            continue

        body = line[1:]
        if not body.strip():
            continue

        sign = line[0]
        stripped = body.strip()
        if current == MANIFEST_PATH:
            ok = ALLOWED_MANIFEST.fullmatch(body)
        elif PKGBUILD_PATH.fullmatch(current):
            ok = any(p.fullmatch(stripped) for p in ALLOWED_PKGBUILD)
        else:
            ok = False

        if not ok:
            problems.append(f"{sanitize(current)}: {sign} {sanitize(body)}")
            continue

        # 'SKIP' is permitted in the grammar so that replacing a SKIP with a
        # real checksum validates, but introducing one is an integrity
        # downgrade: it disables makepkg's check for that source.
        if sign == "+" and "SKIP" in stripped:
            problems.append(
                f"{sanitize(current)}: + {sanitize(body)} "
                f"-- introduces SKIP, disabling the checksum for that source"
            )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repository to inspect (default: .)")
    ap.add_argument(
        "--worktree",
        action="store_true",
        help="inspect unstaged worktree changes instead of the index",
    )
    args = ap.parse_args()
    staged = not args.worktree

    try:
        problems = check_paths_and_modes(args.repo, staged)
        problems += check_content(args.repo, staged)
    except RuntimeError as exc:
        print(f"validator could not run: {exc}", file=sys.stderr)
        return 2

    if problems:
        print("VERDICT: FAIL")
        print()
        print("These changes are not mechanically validatable as a routine version")
        print("bump. Each needs a human to read it against upstream AUR history:")
        print()
        for p in problems:
            print(f"  {p}")
        return 1

    print("VERDICT: PASS")
    print("Every changed line is a literal version, checksum or manifest update.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
