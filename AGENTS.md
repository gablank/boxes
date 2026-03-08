# Agent Guidelines

This file provides instructions for AI coding agents working on this repository.

## Keeping Agent Documentation Up to Date

When you make changes to this repository, you MUST update all documentation to reflect those changes. This includes:

- **`README.md`** -- the user-facing doc; if behavior, commands, or conventions change, it must be updated too
- **`AGENTS.md`** (this file) -- update the repository structure, conventions, or any section that is affected by your changes
- **`.cursor/rules/*.mdc`** -- update any Cursor rules whose content is invalidated by your changes

Examples: if you add a new box, update the repo structure listing. If you change how the CLI works, update the bin/box CLI section *and* the README command table. If you change the image tag format, update every doc that mentions it. Outdated docs are worse than no docs.

## Proactive Self-Improvement

Beyond keeping docs in sync, agents must **proactively** improve this repository and its agent files:

- If a skill, rule, or section of `AGENTS.md` is missing or stale — fix it, even if it wasn't part of the current task.
- After completing any task, look for automation opportunities: a missing `bin/box` command, a useful CI job, a script that belongs in `local-bin/`. Mention these to the user explicitly.
- If you performed a manual multi-step process, suggest how to automate it.

This is enforced by `.cursor/rules/self-improve.mdc`.

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
setup.sh                    One-shot setup script for new users / forks
.github/workflows/
  build.yml                 Nightly + on-push CI build and image cleanup
```

## Image Build Flow

1. A `changes` job detects which paths changed and computes the `date_tag`; on `schedule`/`workflow_dispatch` all flags are forced true
2. `build-base` runs only if `Containerfile.base`, `scripts/`, or `local-bin/` changed
3. `build-priv` and `build-work` each run only if base changed OR their own directory changed; they run in parallel after `build-base`
4. All images are tagged `latest` + `YYYY-MM-DDTHHMM` (e.g. `2026-03-04T0300`, UTC) and pushed to ghcr.io
5. Locally, `box rebuild <name>` pulls the latest image and recreates the container

`<repo-owner>` is derived from `github.repository_owner` in CI — no hardcoding, so forks work out of the box.

## Containerfile Conventions

- `Containerfile.base` installs everything shared: pacman packages, yay, AUR packages, Cursor extensions, system fixes, `scripts/init-user.sh`, and `local-bin/`
- Box-specific Containerfiles (`priv/Containerfile`, `work/Containerfile`) declare `ARG BASE_IMAGE=ghcr.io/gablank/box-base:latest` followed by `FROM ${BASE_IMAGE}`. CI overrides `BASE_IMAGE` to point to the fork owner's registry.
- Build context is always the repo root
- Both base and box Containerfiles accept `BUILD_DATE` and `BUILD_SHA` build args, written to `/etc/box-build-info`
- Always clean caches at the end of a Containerfile (`pacman -Scc --noconfirm`, `rm -rf /var/cache/pacman/pkg/*`)

### Adding a package

- Needed by all boxes: add to `Containerfile.base` (pacman: `pacman -S --noconfirm --needed <pkg>`, AUR: `yay -S --noconfirm --needed <pkg>` as builduser)
- Needed by one box: add to that box's Containerfile

### Adding a Cursor extension

Add it to the extension install loop in `Containerfile.base`.

## bin/box CLI

- Pure bash, uses `distrobox` and `curl`; no `gh` CLI required
- Box argument is always the directory name (`priv`, `work`), not the container name
- Auto-discovers boxes by scanning for `*/distrobox.ini`
- `OWNER` is auto-detected from the git remote URL (`github.com:<owner>/...`); override with `BOX_OWNER` env var
- `box init [owner]` updates the `image=` line in all `distrobox.ini` files to use the specified (or auto-detected) owner; called automatically by `setup.sh`
- `box set-image <box> [tag]` updates the `image=` line in the ini (default: `latest`); does not rebuild
- `box assemble <box>` runs `distrobox assemble create` with whatever is in the ini; does not touch the image tag
- `box assemble-all` assembles all boxes
- `box pull <box> [tag]` pulls the image via `podman pull` without touching the container or ini; uses the tag currently in the ini if none specified
- `box images <box>` lists available tags with a human-readable age column; marks the tag the container is built from with `← current` (green) and the tag the next `assemble` will use with `← next` (yellow)
- Common workflows:
  - Upgrade to latest: `box pull priv && box set-image priv && box assemble priv` (if already on `latest`, skip `set-image`)
  - Rollback: `box set-image priv <tag> && box pull priv <tag> && box assemble priv`
  - Recreate without re-pulling: `box assemble priv`
- To add a command: add `cmd_<name>()` function (use `_` for hyphens in function name), add the case in the dispatch block, update `usage()`, **and add the command name to `_BOX_COMMANDS`** (see Completions sync contract below)
- `box completions <bash|zsh|install>` — prints or installs shell completions; `install` appends `eval "$(box completions <shell>)"` to the user's rc file so completions always reflect the current `bin/box`

## Completions Sync Contract

**Single source of truth for command names:** `_BOX_COMMANDS` array at the top of `bin/box`.

When adding a new command:
1. Add `cmd_<name>()` and the case entry (as above)
2. **Add the name to `_BOX_COMMANDS`** — the CI `lint` job will fail if a case dispatch command is missing from `_BOX_COMMANDS`
3. If the command takes `<box>` as its first argument, also add it to `_BOX_COMMANDS_WITH_BOX`
4. Update the bash and zsh completion heredocs inside `cmd_completions` with the new command (description for zsh)

**Box names** are always discovered dynamically via `box --list-boxes` at completion time — no manual sync needed when adding a new box.

**CI enforcement:** The `lint` job in `.github/workflows/build.yml` runs on every push and verifies:
- `box completions bash` and `box completions zsh` both exit 0 and contain every entry in `_BOX_COMMANDS`
- Every command extracted from the `case` dispatch block exists in `_BOX_COMMANDS`

## Shell Script Style

- Shebang: `#!/usr/bin/env bash`
- Always `set -euo pipefail`
- Quote all variable expansions: `"$var"`
- Use `printf` over `echo` for formatted output
- Use `local` for function-scoped variables
- No comments explaining obvious code

## distrobox.ini Conventions

- `home` and `volume` use `${HOME}` and `${XDG_RUNTIME_DIR}` — expanded by distrobox on the host, never hardcode paths
- `init_hooks` use `${container_user_name}` (a distrobox-init shell variable guaranteed in scope at eval time) — **not** `${USER}`, which is unbound when init_hooks run inside the container
- `distrobox assemble` expands host-side env vars at runtime, so `${HOME}` and `${XDG_RUNTIME_DIR}` resolve correctly for any user
- All boxes use `additional_flags=--security-opt seccomp=unconfined` (required for bubblewrap/bwrap inside the container)
- Tailscale per-box: add `volume=${HOME}/distrobox/<box>/tailscale:/var/lib/tailscale:rw,z` and `--device /dev/net/tun --cap-add NET_ADMIN --cap-add NET_RAW` to `additional_flags`; append `&& tailscaled --statedir=/var/lib/tailscale &` to `init_hooks`; `init-user.sh` auto-adds a `.zshrc` snippet to restart tailscaled on shell open (for post-reboot starts)
- See `.agents/skills/distrobox-ini-conventions/SKILL.md` for the full template and command reference

## Adding a New Box

1. Create `<name>/Containerfile` (FROM box-base, add specific packages, COPY `<name>/local-bin/`)
2. Create `<name>/distrobox.ini` (follow existing pattern)
3. Create `<name>/local-bin/.gitkeep`
4. Add `box-<name>` to the cleanup image list in `.github/workflows/build.yml`
5. In the `changes` job in `.github/workflows/build.yml`: add a `<name>:` paths-filter entry for `<name>/**`, wire the filter output into the `Compute build flags` step so it appends to the `boxes` array. The dynamic matrix (`fromJson`) handles the rest.
6. `bin/box` auto-discovers it -- no changes needed there

**CI path filter maintenance:** The `changes` job in `.github/workflows/build.yml` uses `dorny/paths-filter` to detect changes and builds a dynamic `box_matrix` JSON array consumed by `build-boxes` via `fromJson`. It must be kept in sync with the repo layout:
- New box → add a filter entry for `<name>/**` and wire it into the `boxes` array in the `Compute build flags` step
- New shared directory (e.g. a new top-level dir copied into all images) → add it to the `base:` filter
- Renamed or moved directory → update the matching filter entry

Whenever you add something to CI that is gated by a path filter, document what must be updated here and in the relevant skill.
