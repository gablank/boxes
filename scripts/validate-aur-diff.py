#!/usr/bin/env python3
"""Deterministically classify a vendored AUR bump into a review tier.

The threat this serves: we trust the *upstream developers* whose artifacts the
recipes download, and we do not trust the *AUR packagers* who write the recipes.
Everything a hostile packager controls -- PKGBUILD code, `.install` scriptlets
that run as root at image build time, `.patch` files applied to upstream source,
and local `.sh`/completion files that get installed into the image -- is plain
text inside the diff. So the diff is the whole battlefield, and the job here is
to decide *who reads it*, not to decide that it is safe.

Three outcomes:

  A  Every changed line is a complete literal version/checksum/manifest update
     in an existing PKGBUILD, and versions move forward. The `source=` lines are
     untouched by construction -- any edit to one is non-literal -- so the
     download host stays pinned to the human-reviewed value and a bump can only
     re-point at a different artifact from that same trusted origin. Safe to
     merge mechanically.

  B  A bounded, readable recipe change: ordinary text, modifications or
     additions inside an existing vendored package, within the size caps. This
     is where a hostile packager would actually put a payload, so it is read
     line by line by an isolated model review before anything merges.

  C  Anything outside those bounds -- a deleted or renamed file, a mode or type
     change, binary content, a brand-new vendored package, unreadable bytes, or
     a change too large to review carefully. A human reads these.

Tier A's grammar replaces the old "strip the routine lines and read what's left"
filter, which was unsafe. PKGBUILDs are shell programs, so a line beginning with
`pkgver=` or `sha256sums=` can carry command substitution, a trailing `;` and
another command, or a line continuation. Stripping such lines by prefix told the
reader "nothing but routine version/checksum lines" for a diff that in fact
changed what the build executes. The rule here is inverted and fails closed:
every changed line must match one of a small set of exact literal shapes, and
anything else -- including a line that merely *looks* routine -- leaves tier A.

The candidate PKGBUILD is never sourced, executed, or passed to a shell. Only
the diff text is inspected.

Exit status: 0 tier A, 1 tier B or C, 2 usage error. `--tier-file` writes the
tier letter for a caller that needs to tell B and C apart.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# A literal value: no shell metacharacters at all. This is the whole point of
# the tier A grammar, so keep it strict -- $ ` ( ) ; & | < > \ " ' whitespace
# and newline are all absent by construction.
SAFE_VALUE = r"[A-Za-z0-9._+~:-]+"
HEX40 = r"[0-9a-f]{40}"
CHECKSUM = r"[0-9a-f]{32,128}"

# A single checksum array entry. 'SKIP' is accepted by the grammar so that
# replacing a SKIP with a real checksum validates; introducing one is rejected
# separately in check_content, since it disables an integrity check.
CKSUM_VAL = rf"(?:{CHECKSUM}|SKIP)"
QUOTED_CKSUM = rf"(?:'{CKSUM_VAL}'|\"{CKSUM_VAL}\"|{CKSUM_VAL})"
CKSUM_ARRAY = r"(?:sha[0-9]+sums|md5sums|b2sums)(?:_[a-z0-9_]+)?"
ENTRIES = rf"{QUOTED_CKSUM}(?:[ \t]+{QUOTED_CKSUM})*"

# Assignments whose old and new values tier A compares for forward movement.
ORDERED = re.compile(rf"(pkgver|_pkgver|pkgrel|_commit)=['\"]?({SAFE_VALUE})['\"]?$")

# Two classes of PKGBUILD line never go to a model, however readable they look.
#
# PINNED_LHS is an assignment that pins *which* artifact gets installed. Those
# are exactly the lines tier A's grammar accepts, so one that fails the grammar
# is a version or checksum assignment carrying something else -- the 2026-09-08
# finding, `pkgver=1.2.3$(...)`, which is both a version and a command. There is
# no legitimate version of that line, so trusted code rejects it rather than
# asking anyone's judgment about it.
#
# ORIGIN_LHS assigns *where* an artifact comes from, or what scriptlet runs as
# root at install time. Those lines are the single highest-consequence text in
# the file and they change perhaps once a year per package, so the cost of
# sending them to a human is a review a year and the cost of getting one wrong
# is the whole image. Build-function code that merely mentions `install` or a
# URL is unaffected: this matches only an assignment.
SUBSCRIPT = r"[ \t]*(?:\[[^]\n]*\])?[ \t]*="
PINNED_LHS = re.compile(rf"(?:pkgver|_pkgver|pkgrel|_commit|{CKSUM_ARRAY}){SUBSCRIPT}")
ORIGIN_LHS = re.compile(rf"(?:source|noextract|install|validpgpkeys)(?:_[a-z0-9_]+)?{SUBSCRIPT}")

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
    # quoted with ' or " or not at all -- all three occur in the wild. An array
    # that opens on one line and closes on a later one (herdr-bin, and the
    # default makepkg style) leaves the opening and continuation lines
    # unterminated, so each permitted shape exists with and without its ')'.
    re.compile(rf"{CKSUM_ARRAY}=\($"),
    re.compile(rf"{CKSUM_ARRAY}=\({ENTRIES}\)?$"),
    # Cursor replaces its initial SKIP with sha512sums[0]=<hash>. Bash array
    # subscripts are arithmetic expressions, so allow only a decimal literal.
    re.compile(rf"{CKSUM_ARRAY}\[(?:0|[1-9][0-9]*)\]={QUOTED_CKSUM}$"),
    re.compile(rf"{ENTRIES}\)?$"),
    re.compile(r"\)$"),
]

# pkgbase <TAB> commit <TAB> ISO date
ALLOWED_MANIFEST = re.compile(rf"[a-z0-9][a-z0-9._+-]*\t{HEX40}\t[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$")

PKGBASE = r"[a-z0-9][a-z0-9._+-]*"
# A vendored local source: an ordinary filename, never `.`/`..`, and never a
# name carrying shell metacharacters -- the 2026-09-08 finding was a vendored
# filename interpolated into a `run:` script.
LOCAL_NAME = r"(?!\.\.?$)[A-Za-z0-9._][A-Za-z0-9._+-]*"
PKGBUILD_PATH = re.compile(rf"aur/{PKGBASE}/PKGBUILD$")
PACKAGE_FILE_PATH = re.compile(rf"aur/({PKGBASE})/{LOCAL_NAME}$")
MANIFEST_PATH = "aur/manifest.tsv"

# git's raw format reports these; only an ordinary non-executable file may
# change, and only an in-place edit or a new file inside an existing package.
REGULAR_FILE_MODE = "100644"
ABSENT_MODE = "000000"

# Tier B bounds. A change larger than this is not one a line-by-line reviewer
# holds in their head, and a long plausible-looking refactor in which every
# line is individually benign is the shape a careful reviewer most reliably
# misses. Over the cap is a human's problem, not a bigger prompt.
MAX_REVIEW_LINES = 400
MAX_REVIEW_FILES = 20


def sanitize(text: str) -> str:
    """Render an untrusted line safely for a report.

    The result is only ever written to a file and `cat`-ed, never interpolated
    into a shell command or an Actions expression, but control characters could
    still corrupt a log or smuggle terminal escapes past a reader.
    """
    return "".join(c if c.isprintable() or c == "\t" else f"\\x{ord(c):02x}" for c in text)


def vercmp(one: str, two: str) -> int:
    """Compare two pkgver strings the way pacman's `vercmp` does.

    A faithful port of rpmvercmp: alternating alphabetic and numeric segments
    compared pairwise, numeric beating alphabetic, leading zeros ignored, and a
    trailing alphabetic segment losing to nothing at all (1.0a is older than
    1.0). Ported rather than shelled out to because CI runs on Ubuntu, where
    pacman's binary does not exist.
    """
    if one == two:
        return 0
    i = j = 0
    while i < len(one) and j < len(two):
        # Skip separators; a different separator run length decides on its own.
        si, sj = i, j
        while i < len(one) and not one[i].isalnum():
            i += 1
        while j < len(two) and not two[j].isalnum():
            j += 1
        if (i - si) != (j - sj):
            return -1 if (i - si) < (j - sj) else 1
        if i >= len(one) or j >= len(two):
            break
        numeric = one[i].isdigit()
        ai, bj = i, j
        while i < len(one) and (one[i].isdigit() if numeric else one[i].isalpha()):
            i += 1
        while j < len(two) and (two[j].isdigit() if numeric else two[j].isalpha()):
            j += 1
        a, b = one[ai:i], two[bj:j]
        if not b:
            # The segments are of different kinds; a number outranks a word.
            return 1 if numeric else -1
        if numeric:
            a, b = a.lstrip("0"), b.lstrip("0")
            if len(a) != len(b):
                return -1 if len(a) < len(b) else 1
        if a != b:
            return -1 if a < b else 1
    if i >= len(one) and j >= len(two):
        return 0
    if i >= len(one):
        return 1 if two[j].isalpha() else -1
    return -1 if one[i].isalpha() else 1


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        # Invalid UTF-8 becomes an unprintable surrogate rather than an
        # exception, so check_content rejects it as a control character
        # instead of the classifier dying and telling the caller nothing.
        encoding="utf-8",
        errors="surrogateescape",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def check_paths_and_modes(repo: str, staged: bool) -> tuple[list[str], list[str]]:
    """Split the changed paths into human-only findings and reviewable ones.

    Blocking (tier C): symlinks (120000), submodule links (160000), a newly
    executable file (100755), type changes, deletions, renames, and any file in
    a package directory that does not already exist -- adding or removing a
    vendored package is a manual pull request, not a nightly bump.

    Reviewable (tier B): an edited or added ordinary file inside an existing
    vendored package that is not the PKGBUILD or the manifest -- a scriptlet, a
    patch, a wrapper, a completion. Legitimate upstream churn, and the best
    hiding place a packager has, so it goes to review rather than merging.
    """
    args = ["diff", "--raw", "-z", "--no-renames"]
    if staged:
        args.append("--cached")
    args += ["--", "aur/"]
    raw = git(repo, *args)

    blocking: list[str] = []
    reviewable: list[str] = []
    paths_seen: list[str] = []
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
            blocking.append(f"unparseable git raw entry: {sanitize(meta)}")
            i += 1
            continue
        old_mode, new_mode, _, _, status = parts[:5]
        path = fields[i + 1] if i + 1 < len(fields) else ""
        i += 2

        shown = sanitize(path)
        if status not in ("M", "A"):
            blocking.append(
                f"{shown}: status {status} -- a bump only edits or adds files "
                f"(deleting, renaming or retyping one is a manual pull request)"
            )
            continue
        if new_mode != REGULAR_FILE_MODE or old_mode not in (REGULAR_FILE_MODE, ABSENT_MODE):
            blocking.append(
                f"{shown}: file mode {old_mode} -> {new_mode}, expected "
                f"{REGULAR_FILE_MODE} (symlink, submodule or executable bit)"
            )
            continue
        paths_seen.append(path)
        match = PACKAGE_FILE_PATH.fullmatch(path)
        if path != MANIFEST_PATH and not match:
            blocking.append(f"{shown}: not a file inside a vendored package")
            continue
        # A new file may only appear in a package this repository already
        # vendors -- including a new PKGBUILD, which would *be* a new package.
        if status == "A" and match:
            recipe = f'{"HEAD" if staged else ":0"}:aur/{match.group(1)}/PKGBUILD'
            probe = subprocess.run(["git", "-C", repo, "cat-file", "-e", recipe],
                                   capture_output=True, check=False)
            if probe.returncode != 0:
                blocking.append(
                    f"{shown}: no such vendored package -- adding one is a manual pull request")
                continue
        if path == MANIFEST_PATH or PKGBUILD_PATH.fullmatch(path):
            continue
        reviewable.append(f"{shown}: {'new file' if status == 'A' else 'edited'} inside a vendored package")
    return blocking, reviewable, paths_seen


def check_content(repo: str, staged: bool) -> tuple[list[str], list[str], dict]:
    """Inspect every added and removed line.

    Removed lines are checked too: deleting a checksum entry or a chunk of a
    build function changes behaviour just as much as adding one.

    Returns (blocking, nonliteral, assignments, unreviewed): blocking findings
    put the change in tier C, nonliteral lines take it out of tier A into tier
    B, assignments carries the before/after ordered values for the tier A
    version check, and unreviewed names the files whose changes are not all
    literal -- the ones a tier B reviewer has to read in full.
    """
    args = ["diff", "-U0", "--no-ext-diff", "--no-textconv", "--no-renames"]
    if staged:
        args.append("--cached")
    args += ["--", "aur/"]
    patch = git(repo, *args)

    blocking: list[str] = []
    nonliteral: list[str] = []
    assignments: dict = {}
    unreviewed: set[str] = set()
    changed = 0
    current = ""
    for line in patch.splitlines():
        if line.startswith(("Binary files ", "GIT binary patch")):
            blocking.append(f"binary change cannot be reviewed as text: {sanitize(line)}")
            continue
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
        changed += 1

        sign = line[0]
        stripped = body.strip()
        # A control character in changed text is never legitimate here and is a
        # classic way to hide what a line does from whoever reads the diff.
        hidden = [c for c in body if not c.isprintable() and c != "\t"]
        if hidden:
            blocking.append(
                f"{sanitize(current)}: {sign} {sanitize(body)} "
                f"-- contains a control character, which cannot be reviewed as written"
            )
            continue

        if current == MANIFEST_PATH:
            ok = bool(ALLOWED_MANIFEST.fullmatch(body))
        elif PKGBUILD_PATH.fullmatch(current):
            ok = any(p.fullmatch(stripped) for p in ALLOWED_PKGBUILD)
            order = ORDERED.fullmatch(stripped)
            if ok and order:
                side = assignments.setdefault(current, {"-": {}, "+": {}})
                side[sign][order.group(1)] = order.group(2)
        else:
            ok = False

        if not ok:
            unreviewed.add(current)
            finding = f"{sanitize(current)}: {sign} {sanitize(body)}"
            if PKGBUILD_PATH.fullmatch(current) and PINNED_LHS.match(stripped):
                blocking.append(finding + " -- a version or checksum assignment that is not a "
                                          "plain literal value")
            elif PKGBUILD_PATH.fullmatch(current) and ORIGIN_LHS.match(stripped):
                blocking.append(finding + " -- changes where an artifact comes from or what "
                                          "runs at install time")
            else:
                nonliteral.append(finding)
            continue

        # 'SKIP' is permitted in the grammar so that replacing a SKIP with a
        # real checksum validates, but introducing one is an integrity
        # downgrade: it disables makepkg's check for that source. There is no
        # legitimate packager reason to add one to a recipe that had a real
        # checksum, so it never becomes a question of judgment.
        if sign == "+" and "SKIP" in stripped:
            blocking.append(
                f"{sanitize(current)}: + {sanitize(body)} "
                f"-- introduces SKIP, disabling the checksum for that source"
            )

    if changed > MAX_REVIEW_LINES:
        blocking.append(
            f"{changed} changed lines exceeds the {MAX_REVIEW_LINES}-line review cap "
            f"-- too large to read line by line with any confidence"
        )
    return blocking, nonliteral, assignments, unreviewed


def check_version_order(assignments: dict) -> list[str]:
    """Versions must move forward.

    Tier A leaves every `source=` line untouched, so the download host stays
    pinned -- but `pkgver` and `_commit` are interpolated *into* those URLs. A
    packager who cannot change where an artifact comes from can still choose
    *which* artifact by moving the version backwards, pinning the image to a
    known-vulnerable release.

    This goes to a human rather than to the model review: telling a downgrade
    attack from a legitimate upstream revert needs the upstream history, which
    the reviewer is deliberately not given.
    """
    problems: list[str] = []
    for path, sides in sorted(assignments.items()):
        old, new = sides["-"], sides["+"]
        moved = [k for k in ("pkgver", "_pkgver", "_commit") if k in new or k in old]
        if "pkgver" in new or "pkgver" in old:
            if "pkgver" not in new or "pkgver" not in old:
                problems.append(f"{path}: pkgver was added or removed rather than changed")
            elif vercmp(new["pkgver"], old["pkgver"]) <= 0:
                problems.append(
                    f"{path}: pkgver {sanitize(old['pkgver'])} -> {sanitize(new['pkgver'])} "
                    f"does not move forward"
                )
        elif moved:
            # _commit and _pkgver have no order of their own; the only evidence
            # that one moves forward is the pkgver that travels with it.
            problems.append(
                f"{path}: {', '.join(sorted(moved))} changed without a pkgver bump, "
                f"so the new artifact cannot be shown to be newer"
            )
        elif "pkgrel" in new and "pkgrel" in old and int(new["pkgrel"]) <= int(old["pkgrel"]):
            problems.append(
                f"{path}: pkgrel {old['pkgrel']} -> {new['pkgrel']} does not move forward"
            )
    return problems


def classify(repo: str, staged: bool) -> tuple[str, list[str], list[str], list[str]]:
    """Return (tier, blocking findings, findings needing a read, files to read).

    The last value is the files a tier B reviewer must see in full: the ones
    whose changes are not all literal. A PKGBUILD that only moved a version and
    a checksum is fully described by the diff, so sending its whole text would
    add weight without adding evidence -- and with a dozen vendored packages a
    nightly all-bump would otherwise grow past the payload limit and start
    failing instead of merging.
    """
    path_blocking, path_reviewable, paths = check_paths_and_modes(repo, staged)
    content_blocking, nonliteral, assignments, unreviewed = check_content(repo, staged)
    blocking = path_blocking + content_blocking + check_version_order(assignments)
    reviewable = path_reviewable + nonliteral
    # A file outside the PKGBUILD/manifest grammar has no literal form at all,
    # so every changed line in it counts as unreviewed by construction.
    needs_reading = sorted(unreviewed | {
        p for p in paths if p != MANIFEST_PATH and not PKGBUILD_PATH.fullmatch(p)})
    if blocking:
        return "C", blocking, reviewable, needs_reading
    if len(needs_reading) > MAX_REVIEW_FILES:
        return ("C", [f"{len(needs_reading)} files need a full read, over the "
                      f"{MAX_REVIEW_FILES}-file review cap"], reviewable, needs_reading)
    if reviewable:
        return "B", [], reviewable, needs_reading
    return "A", [], [], []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repository to inspect (default: .)")
    ap.add_argument(
        "--worktree",
        action="store_true",
        help="inspect unstaged worktree changes instead of the index",
    )
    ap.add_argument("--tier-file", help="write the tier letter (A, B or C) to this file")
    ap.add_argument("--files-file",
                    help="write the files a reviewer must read in full, one per line")
    args = ap.parse_args()
    staged = not args.worktree

    try:
        tier, blocking, reviewable, needs_reading = classify(args.repo, staged)
    except RuntimeError as exc:
        print(f"validator could not run: {exc}", file=sys.stderr)
        return 2

    if args.tier_file:
        with open(args.tier_file, "w") as handle:
            handle.write(tier)
    if args.files_file:
        with open(args.files_file, "w") as handle:
            handle.write("".join(f"{p}\n" for p in needs_reading))

    if tier == "A":
        print("TIER: A -- merge without further review")
        print("Every changed line is a literal version, checksum or manifest update,")
        print("no source definition moved, and every version moves forward.")
        return 0

    if tier == "B":
        print("TIER: B -- recipe change, read line by line before merging")
        print()
        print("These changes are not routine literal updates. They are bounded and")
        print("readable, so an isolated review reads every line against what it does")
        print("at build, install and run time:")
        print()
    else:
        print("TIER: C -- human review required")
        print()
        print("These changes are outside what can be reviewed from the diff alone.")
        print("Each needs a human to read it against upstream AUR history:")
        print()
        for problem in blocking:
            print(f"  {problem}")
        if reviewable:
            print()
            print("Also changed:")
            print()
    for problem in reviewable:
        print(f"  {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
