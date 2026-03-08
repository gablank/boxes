# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Distrobox container environments (Arch Linux) built via GitHub Actions and managed locally with the `box` CLI. Designed to be forked — CI auto-publishes images to the fork owner's GHCR.

Two boxes exist: `priv` (personal dev) and `work` (adds kubectl, k9s, qemu, glab).

## Architecture

**Image layering:** `Containerfile.base` builds a shared base image with all common packages. Each box (`priv/Containerfile`, `work/Containerfile`) is a thin layer on top via `ARG BASE_IMAGE`. CI injects the fork owner's registry into the build arg.

**CLI:** `bin/box` is the host-side management tool (pure Bash, ~530 lines, 13 commands). Auto-discovers boxes by scanning for `*/distrobox.ini`. Box argument is the directory name (`priv`, `work`), not the container name (`privbox`, `workbox`).

**Runtime init:** `scripts/init-user.sh` runs once on first container start via `init_hooks` in `distrobox.ini`.

## CI/CD

Workflow: `.github/workflows/build.yml` — runs on push to main and nightly at 03:00 UTC.

Jobs: `lint` (completions sync check) → `changes` (path-filter detection, matrix generation) → `build-base` (conditional) → `build-boxes` (matrix, parallel) → `cleanup` (delete images >14 days).

Path-based build skipping: base rebuilds only when `Containerfile.base`, `scripts/`, or `local-bin/` change. Each box rebuilds when base or its own directory changes. Scheduled/manual runs rebuild everything.

**Lint job enforces:** the `_BOX_COMMANDS` array in `bin/box` must match the case dispatch block and completions output. This is the completions sync contract.

## Linting / Testing

There is no test suite beyond the CI lint job. To run the lint checks locally:

```bash
# Verify completions output contains all commands
bash -c 'source <(bin/box completions bash); _box_completions'
bin/box completions zsh | grep -c 'commands'

# Verify _BOX_COMMANDS matches case dispatch (what CI does)
grep '_BOX_COMMANDS=' bin/box
grep -oP '^\s+\K[a-z-]+(?=\))' bin/box  # extract case arms
```

## Key Conventions

### Shell style
- Shebang: `#!/usr/bin/env bash`, always `set -euo pipefail`
- Quote all variables, use `printf` over `echo`, use `local` for function scope
- ANSI colors via `$'\033[...'` (dollar-quote syntax)

### Containerfiles
- Use `--noconfirm --needed` for pacman installs
- All-boxes packages go in `Containerfile.base`; box-specific in `<box>/Containerfile`
- Build context is repo root, not the box subdirectory

### distrobox.ini
- Host-side env vars (`${HOME}`, `${XDG_RUNTIME_DIR}`) expanded by distrobox at runtime
- In `init_hooks`, use `${container_user_name}` (NOT `${USER}` — unbound during eval)
- All boxes require `--security-opt seccomp=unconfined` for bubblewrap/bwrap

### Git commits
- Format: `<type>(<scope>): <message>` — types: feat, fix, refactor, docs, ci, chore
- Split logically: CI, docs, and rule changes get separate commits
- Never push unless the user explicitly requests it

## Maintenance Contracts

When adding a new box, you must update: the box's `Containerfile`, `distrobox.ini`, CI path filters in `build.yml` (both the `changes` filter and the `box_matrix` generation), and the README boxes table.

When adding a new `bin/box` command: add to `_BOX_COMMANDS` array, add case dispatch, and verify completions stay in sync (CI enforces this).

## Public Repository

Never add secrets, tokens, credentials, personal data, or private keys. Use runtime env vars for secrets.

## Agent Docs

Detailed conventions live in `.agents/skills/` (repo-overview, shell-style, containerfile-conventions, distrobox-ini-conventions, box-cli-conventions, adding-a-box) and `.agents/rules/` (core, self-improve). Update these when behavior changes.
