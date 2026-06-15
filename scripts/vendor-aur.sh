#!/usr/bin/env bash
# Re-vendor AUR PKGBUILDs into aur/<pkgbase>/ from the AUR, printing a diff so the
# change can be vetted before committing. The images build only from these
# committed copies (Tier-3 supply-chain control) — see aur/README.md.
#
# Usage: vendor-aur.sh <pkgbase>... | --all
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
aur_dir="$repo_root/aur"
manifest="$aur_dir/manifest.tsv"

usage() { printf 'Usage: %s <pkgbase>... | --all\n' "${0##*/}"; }

mapfile -t vendored < <(find "$aur_dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)

targets=()
case "${1:-}" in
  ''|-h|--help) usage; exit 0 ;;
  --all)
    if [ "${#vendored[@]}" -eq 0 ]; then printf 'no vendored packages yet\n' >&2; exit 1; fi
    targets=("${vendored[@]}")
    ;;
  *) targets=("$@") ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

update_manifest() {
  local base=$1 commit=$2 date=$3 t
  t="$(mktemp)"
  { [ -f "$manifest" ] && grep -vE "^${base}	" "$manifest" || true
    printf '%s\t%s\t%s\n' "$base" "$commit" "$date"
  } | sort > "$t"
  mv "$t" "$manifest"
}

for base in "${targets[@]}"; do
  printf '\n=== %s ===\n' "$base"
  git clone --quiet "https://aur.archlinux.org/$base.git" "$tmp/$base"
  commit="$(git -C "$tmp/$base" rev-parse HEAD)"

  # Keep only build-relevant files; drop VCS/metadata and build artifacts.
  rm -rf "$tmp/$base/.git"
  rm -f "$tmp/$base/.SRCINFO" "$tmp/$base/.nvchecker.toml" "$tmp/$base/.gitignore"

  if [ -d "$aur_dir/$base" ]; then
    if diff -ruN "$aur_dir/$base" "$tmp/$base"; then
      printf '(no change)\n'
    fi
  else
    printf '(new package)\n'
  fi

  rm -rf "$aur_dir/$base"
  cp -a "$tmp/$base" "$aur_dir/$base"
  update_manifest "$base" "$commit" "$(date -u +%Y-%m-%d)"
done

printf '\nReview the diff above, then: git add aur/ && git commit\n'
