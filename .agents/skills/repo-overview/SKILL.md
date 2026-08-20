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
- `bin/box` is the CLI management tool (assemble, enter, set-image, pull, images, etc.)

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

## Image flow

1. CI builds `box-base` from `Containerfile.base`
2. CI builds `box-priv`, `box-work`, and `box-dev` from their respective Containerfiles (FROM box-base)
3. All images are tagged `latest` + `YYYY-MM-DDTHHMM` (UTC) and pushed to ghcr.io
4. Locally, `box upgrade <name>` pulls latest and recreates the container
