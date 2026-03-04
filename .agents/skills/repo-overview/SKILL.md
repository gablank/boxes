---
name: repo-overview
description: Repository structure and architecture overview. Use when exploring the codebase, onboarding, or needing to understand how the repo is organized, how images are built, or what lives where.
---

# Repository Overview

This repo defines distrobox container environments built via CI and managed locally with `bin/box`.

## Architecture

- `Containerfile.base` - shared base image (Arch Linux + pacman + yay + AUR packages + Cursor extensions)
- `priv/Containerfile`, `work/Containerfile` - thin layers adding box-specific packages
- Images are built nightly by GitHub Actions and pushed to `ghcr.io/gablank/box-*`
- `distrobox.ini` files point to the pre-built images; `distrobox assemble` just pulls and creates
- `scripts/init-user.sh` handles lightweight user-home setup at first run
- `bin/box` is the CLI management tool (rebuild, enter, revert, images, etc.)

## Key directories

| Path | Purpose |
|------|---------|
| `Containerfile.base` | Shared base image definition |
| `priv/`, `work/` | Per-box Containerfile, distrobox.ini, and local-bin/ |
| `local-bin/` | Custom scripts/binaries installed into ALL boxes |
| `{box}/local-bin/` | Custom scripts/binaries installed into that specific box |
| `scripts/` | Runtime init scripts baked into the base image |
| `bin/box` | Host-side CLI for managing boxes |
| `.github/workflows/` | CI build and cleanup workflows |

## Image flow

1. CI builds `box-base` from `Containerfile.base`
2. CI builds `box-priv` and `box-work` from their respective Containerfiles (FROM box-base)
3. All images are tagged `latest` + `YYYY-MM-DD` and pushed to ghcr.io
4. Locally, `box rebuild <name>` pulls latest and recreates the container
