# Agent Guidelines

This file provides instructions for AI coding agents working on this repository.

## Keeping Agent Documentation Up to Date — BLOCKING

Documentation drift is the #1 maintenance failure in this repo. **Every code change MUST be accompanied by a documentation audit.** A task is not complete until docs are in sync.

The full protocol — what to check before starting, the per-file audit checklist, and the "removing a workaround" greppable-cleanup rule — lives in `.agents/rules/core.mdc` and is loaded automatically (alwaysApply). Read it. The short version:

- **Before** changing code, read the docs that describe the area you're about to change.
- **After** changing code, walk the per-file checklist in `core.mdc` and update every affected doc surface (`README.md`, `AGENTS.md`, the relevant `.agents/skills/*/SKILL.md`).
- When **removing** a workaround/alias/feature, `grep -rn` the repo for stale references and delete them all.

Outdated docs are worse than no docs.

## Proactive Self-Improvement

Beyond keeping docs in sync, agents must **proactively** improve this repository and its agent files:

- If a skill, rule, or section of `AGENTS.md` is missing or stale — fix it, even if it wasn't part of the current task.
- After completing any task, look for automation opportunities: a missing `bin/box` command, a useful CI job, a script that belongs in `local-bin/`. Mention these to the user explicitly.
- If you performed a manual multi-step process, suggest how to automate it.

This is enforced by `.cursor/rules/self-improve.mdc`.

## Active Workarounds — Always Ask

**distrobox-enter `--pty` patch (2026-04-17):** The host has a patched copy of `distrobox-enter` in `~/.local/bin/` that removes the `--pty` flag from the `unshare_groups` su block. This works around distrobox issue [#2011](https://github.com/89luca89/distrobox/issues/2011) where newer util-linux passes `--pty` through to zsh. The upstream fix is in PR [#2053](https://github.com/89luca89/distrobox/pull/2053). **At the start of every conversation, ask the user whether this patch has been reverted.**

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
  box.toml                  Container definition — source of truth (distrobox.ini is generated, gitignored)
  local-bin/                Scripts/binaries installed only into privbox
work/
  Containerfile             Thin layer on base for workbox (adds kubectl, k9s, qemu, glab)
  box.toml                  Container definition — source of truth
  local-bin/                Scripts/binaries installed only into workbox
dev/
  Containerfile             Thin layer on base for devbox (no init, no root — for developing box itself)
  box.toml                  Container definition — source of truth
local-bin/                  Scripts/binaries installed into ALL boxes
scripts/
  init-root.sh              First-start root init (chsh, /etc/environment) — no TTY
  init-user.sh              First-start user init (~/.ssh, .zshrc, rustup) — no TTY, no sudo
  shell-init.sh             Sourced from .zshrc on every shell open — runtime env, services
  compile-box-toml.py       Compiles box.toml → distrobox.ini (Python 3.11+, stdlib tomllib)
bin/
  box                       Host-side CLI for managing boxes
setup.sh                    One-shot setup script for new users / forks
.github/workflows/
  build.yml                 Nightly + on-push CI build and image cleanup
```

## Image Build Flow

1. A `changes` job detects which paths changed and computes the `date_tag`; on `schedule`/`workflow_dispatch` all flags are forced true
2. `build-base` runs only if `Containerfile.base`, `scripts/`, or `local-bin/` changed
3. `build-priv`, `build-work`, and `build-dev` each run only if base changed OR their own directory changed; they run in parallel after `build-base`
4. All images are tagged `latest` + `YYYY-MM-DDTHHMM` (e.g. `2026-03-04T0300`, UTC) and pushed to ghcr.io
5. Locally, `box pull <name> && box assemble <name>` pulls the latest image and recreates the container

`<repo-owner>` is derived from `github.repository_owner` in CI — no hardcoding, so forks work out of the box.

## Containerfile Conventions

- `Containerfile.base` installs everything shared: pacman packages, yay, AUR packages, Cursor extensions, system fixes, the three `scripts/` init scripts (init-root.sh, init-user.sh, shell-init.sh), and `local-bin/`
- Box-specific Containerfiles (`priv/Containerfile`, `work/Containerfile`, `dev/Containerfile`) declare `ARG BASE_IMAGE=ghcr.io/gablank/box-base:latest` followed by `FROM ${BASE_IMAGE}`. CI overrides `BASE_IMAGE` to point to the fork owner's registry.
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
- Auto-discovers boxes by scanning for `*/box.toml`
- `OWNER` is auto-detected from the git remote URL (`github.com:<owner>/...`); override with `BOX_OWNER` env var
- `box init [owner]` updates the `image = ` line in all `box.toml` files (then recompiles to `distrobox.ini`) to use the specified (or auto-detected) owner; called automatically by `setup.sh`
- `box set-image <box> [tag]` updates the `image = ` line in `box.toml` and recompiles (default: `latest`); does not rebuild
- `box assemble <box>` recompiles `box.toml` → `distrobox.ini` and runs `distrobox assemble create`; does not touch the image tag
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

## box.toml Conventions

`box.toml` is the source of truth; `distrobox.ini` is generated by `scripts/compile-box-toml.py` and gitignored. **Never edit the ini directly.**

- `home` and `[[mount-dir]]` host paths use `${HOME}` / `${XDG_RUNTIME_DIR}` — expanded by distrobox on the host, never hardcode paths
- `init_hooks` use `${container_user_name}` (a distrobox-init shell variable guaranteed in scope at eval time) — **not** `${USER}`, which is unbound when init_hooks run inside the container
- `[[mount-dir]]` entries become `volume=` lines (auto-created on host); `[[mount-file]]` entries become `--volume` flags in `additional_flags` (must already exist)
- All boxes use `--security-opt seccomp=unconfined` (required for bubblewrap/bwrap inside the container)
- **Tailscale per-box**: each box has its own tailscale node (different tailnet per box) via `unshare_netns=true`. The box's user namespace owns the netns, making `CAP_NET_ADMIN` valid for `TUNSETIFF`. Setup:
  - `unshare_netns=true`
  - `[[mount-dir]]` for `${HOME}/distrobox/<box>/tailscale:/var/lib/tailscale` — persists auth state across recreates
  - `--device /dev/net/tun --cap-add NET_ADMIN --cap-add NET_RAW` in `additional_flags`
  - **No init_hooks tweaks needed.** The base image ships a systemd drop-in that runs `tailscaled` with `--socket=/var/run/tailscale/box.sock` and a `/usr/bin/tailscale` wrapper that injects the same flag. This sidesteps the issue where distrobox-init symlinks the host's tailscale socket over the default path inside the container. See `Containerfile.base` for the wrapper definition; `IgnorePkg` keeps in-container `pacman -Syu` from overwriting it.
  - After first `box assemble <box>`, run `tailscale up` inside the box to authenticate
- **Docker-compose + work tailnet**: to make compose services reachable from the work box *and* on the work tailnet, add `network_mode: "container:workbox"` to each service in the compose file. Services then share workbox's network namespace; use `localhost:PORT` to reach them from the box.
- See `.agents/skills/box-toml-conventions/SKILL.md` for the full template and field reference

## Adding or Removing a Box

Follow the complete checklist in `.agents/skills/adding-a-box/SKILL.md`. It covers creating the box directory, updating CI, and updating all documentation files.

**CI path filter maintenance:** The `changes` job in `.github/workflows/build.yml` uses `dorny/paths-filter` to detect changes and builds a dynamic `box_matrix` JSON array consumed by `build-boxes` via `fromJson`. It must be kept in sync with the repo layout:
- New box → add a filter entry for `<name>/**` and wire it into the `boxes` array in the `Compute build flags` step
- New shared directory (e.g. a new top-level dir copied into all images) → add it to the `base:` filter
- Renamed or moved directory → update the matching filter entry

Whenever you add something to CI that is gated by a path filter, document what must be updated here and in the relevant skill.
