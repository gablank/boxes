---
name: repo-overview
description: Repository structure and architecture overview. Use when exploring the codebase, onboarding, or needing to understand how the repo is organized, how images are built, or what lives where.
---

# Repository Overview

This repo defines distrobox container environments built via CI and managed locally with `bin/box`.

## Architecture

- `Containerfile.base` - shared base image (Arch Linux + pacman + AUR packages built from vendored PKGBUILDs + Cursor extensions)
- `aur/` - vetted AUR PKGBUILDs vendored per pkgbase; the base image builds AUR packages only from these, never fetching from the AUR (supply-chain control; see `aur/README.md`)
- `priv/Containerfile`, `work/Containerfile`, `dev/Containerfile` - thin layers adding box-specific packages
- Images are built by GitHub Actions on every push to `main` and nightly, and pushed to `ghcr.io/<repo-owner>/box-*` (derived from `github.repository_owner`, so forks build to their own registry)
- `box.toml` files (one per box) are the source of truth; `scripts/compile-box-toml.py` compiles them to `distrobox.ini` (gitignored). `distrobox assemble` then pulls and creates the container.
- `scripts/init-root.sh`, `init-user.sh`, `shell-init.sh`, and `shell-env.sh` are the four baked-in init scripts (root first-start, user first-start, every-interactive-shell, every-shell-including-non-interactive, respectively)
- `scripts/box-brief.md` is not a script: it is the agent brief baked into the image and loaded by Claude Code (`/etc/claude-code/CLAUDE.md`) and Codex (`~/.codex/AGENTS.md` symlink) at the start of every session in every box
- `bin/box` is the CLI management tool (assemble, enter, set-image, pull, images, etc.)
- `.github/workflows/aur-bump.yml` runs audit → publish → review on main via schedule/manual dispatch only; PR events cannot start the caller. `scripts/trigger-aur-review.py` checks publisher metadata and requires main's eligibility status to be bound to GitHub Actions. It validates candidate Git objects without checking them out, then sends seven fixed identifiers plus a zero-context `diff` through the routine API using the main-only `aur-review` environment token. No PR prose, discussion, commit messages or unchanged source enters the payload. The prompt permits only reviewing that diff and one SHA-bound merge; it cannot itself revoke read tools or suppress auto-loaded repository instructions. Keep the eight-field payload, branch format and `.github/aur-vet-prompt.md` synchronized; deployment, permissions, read isolation and recovery are documented in `aur/README.md`. Its offline security tests run in CI; both scripts are excluded from base-image path filtering.

## Key directories

| Path | Purpose |
|------|---------|
| `Containerfile.base` | Shared base image definition |
| `priv/`, `work/`, `dev/` | Per-box Containerfile, box.toml, and box-specific extras (`local-bin/`; work also has `systemd-user/`) |
| `local-bin/` | Custom scripts/binaries installed into ALL boxes |
| `{box}/local-bin/` | Custom scripts/binaries installed into that specific box |
| `scripts/` | Runtime init scripts baked into the base image, plus `vendor-aur.sh` (re-vendor AUR PKGBUILDs) |
| `aur/` | Vetted AUR PKGBUILDs vendored per pkgbase (images build only from these) |
| `bin/box` | Host-side CLI for managing boxes |
| `.github/workflows/` | CI build and cleanup workflows |
| `.githooks/pre-push` | Opt-in per-clone workflow YAML validation of pushed commits; see README developer setup |

`scripts/check-workflow-yaml.py` uses Mike Farah's yq v4 (the dev image's `go-yq`
package) in both CI and the push hook. `scripts/test-workflow-yaml.py` exercises
real pushes to local repositories without network access.

## Image flow

1. CI builds `box-base` from `Containerfile.base`
2. CI builds `box-priv`, `box-work`, and `box-dev` from their respective Containerfiles (FROM box-base)
3. All images are tagged `latest` + `YYYY-MM-DDTHHMM` (UTC) and pushed to ghcr.io
4. Locally, `box upgrade <name>` pulls latest and recreates the container
