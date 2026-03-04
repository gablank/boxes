# Agent Guidelines

This file provides instructions for AI coding agents working on this repository.

## Keeping Agent Documentation Up to Date

When you make changes to this repository, you MUST update the agent documentation to reflect those changes. This includes:

- **`AGENTS.md`** (this file) -- update the repository structure, conventions, or any section that is affected by your changes
- **`.cursor/rules/*.mdc`** -- update any Cursor rules whose content is invalidated by your changes

Examples: if you add a new box, update the repo structure listing. If you change how the CLI works, update the bin/box CLI section. If you add a new convention, document it. Agent documentation that is out of date is worse than no documentation.

## PUBLIC REPOSITORY -- READ THIS FIRST

This repository is **public on GitHub**. Every file is visible to the entire internet.

- **NEVER** add secrets, tokens, API keys, passwords, or credentials of any kind
- **NEVER** add personal data: email addresses, phone numbers, private IPs, internal hostnames
- **NEVER** add private SSH keys, GPG keys, or certificates
- **NEVER** hardcode authentication tokens for any service

If something needs a secret at runtime, use environment variables. Document the required env var and read it at runtime -- never bake it into images or check it into the repo.

## Repository Structure

This repo defines distrobox container environments built via CI and managed locally with `bin/box`.

```
Containerfile.base          Shared base image (Arch Linux + pacman + yay + AUR + Cursor extensions)
priv/
  Containerfile             Thin layer on base for privbox
  distrobox.ini             Container definition (managed by bin/box)
  local-bin/                Scripts/binaries installed only into privbox
work/
  Containerfile             Thin layer on base for workbox (adds kubectl, k9s, qemu, glab)
  distrobox.ini             Container definition (managed by bin/box)
  local-bin/                Scripts/binaries installed only into workbox
local-bin/                  Scripts/binaries installed into ALL boxes
scripts/
  init-user.sh              Lightweight runtime init (ssh, zshrc, env vars, chsh)
bin/
  box                       Host-side CLI for managing boxes
.github/workflows/
  build.yml                 Nightly + on-push CI build and image cleanup
```

## Image Build Flow

1. GitHub Actions builds `ghcr.io/gablank/box-base` from `Containerfile.base`
2. Then builds `ghcr.io/gablank/box-priv` and `ghcr.io/gablank/box-work` in parallel (FROM box-base)
3. All images are tagged `latest` + `YYYY-MM-DD` and pushed to ghcr.io
4. Locally, `box rebuild <name>` pulls the latest image and recreates the container

## Containerfile Conventions

- `Containerfile.base` installs everything shared: pacman packages, yay, AUR packages, Cursor extensions, system fixes, `scripts/init-user.sh`, and `local-bin/`
- Box-specific Containerfiles (`priv/Containerfile`, `work/Containerfile`) are `FROM ghcr.io/gablank/box-base:latest` and add only box-specific packages and `{box}/local-bin/`
- Build context is always the repo root
- Both base and box Containerfiles accept `BUILD_DATE` and `BUILD_SHA` build args, written to `/etc/box-build-info`
- Always clean caches at the end of a Containerfile (`pacman -Scc --noconfirm`, `rm -rf /var/cache/pacman/pkg/*`)

### Adding a package

- Needed by all boxes: add to `Containerfile.base` (pacman: `pacman -S --noconfirm --needed <pkg>`, AUR: `yay -S --noconfirm --needed <pkg>` as builduser)
- Needed by one box: add to that box's Containerfile

### Adding a Cursor extension

Add it to the extension install loop in `Containerfile.base`.

## bin/box CLI

- Pure bash, uses `distrobox` and `gh` CLI
- Box argument is always the directory name (`priv`, `work`), not the container name
- Auto-discovers boxes by scanning for `*/distrobox.ini`
- `box rebuild` resets the `image=` line to `:latest`; `box revert` pins to a date tag
- To add a command: add `cmd_<name>()` function, add the case in the dispatch block, update `usage()`

## Shell Script Style

- Shebang: `#!/usr/bin/env bash`
- Always `set -euo pipefail`
- Quote all variable expansions: `"$var"`
- Use `printf` over `echo` for formatted output
- Use `local` for function-scoped variables
- No comments explaining obvious code

## distrobox.ini Conventions

- `home`, `volume`, and `init_hooks` use `${HOME}`, `${XDG_RUNTIME_DIR}`, and `${USER}` — never hardcode paths or usernames
- `distrobox assemble` expands env vars at runtime, so these resolve correctly for any user

## Adding a New Box

1. Create `<name>/Containerfile` (FROM box-base, add specific packages, COPY `<name>/local-bin/`)
2. Create `<name>/distrobox.ini` (follow existing pattern)
3. Create `<name>/local-bin/.gitkeep`
4. Add the box name to the matrix in `.github/workflows/build.yml` and the cleanup image list
5. `bin/box` auto-discovers it -- no changes needed there
