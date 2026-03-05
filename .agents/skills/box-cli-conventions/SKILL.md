---
name: box-cli-conventions
description: Conventions for the bin/box CLI tool. Use when modifying bin/box, adding commands, or changing how box management works.
---

# bin/box CLI Conventions

## Design principles

- Pure bash, no external dependencies beyond `distrobox`, `curl`, and standard coreutils; no `gh` CLI required
- Resolves repo root from its own location so it works from any working directory
- Auto-discovers boxes by scanning for `*/distrobox.ini` in the repo root
- The box argument is always the directory name (`priv`, `work`), not the container name (`privbox`, `workbox`)

## Command responsibilities

Each command has exactly one responsibility:

- `set-image <box> [tag]` — updates `image=` in the ini (default: `latest`); no pull, no assemble
- `assemble <box>` — runs `distrobox assemble create` with the current ini; no image tag manipulation
- `assemble-all` — calls `assemble` for each discovered box
- `pull <box> [tag]` — `podman pull`; no ini change, no assemble
- `images <box>` — lists registry tags; marks the tag the container is built from with `← current` (green), and the tag the next `assemble` will use with `← next` (yellow); `← current` uses `podman inspect` so it appears on stopped containers too

## Image tag management

- The `image=` line in distrobox.ini is managed by `set-image` and `init`; manual edits are fine
- Old `YYYY-MM-DD` tags are still supported by `time_ago()` alongside the current `YYYY-MM-DDTHHMM` format
- `images` uses `_image_markers()` (private helper, prefixed `_`) to annotate tags; it checks the ini tag only

## Common workflows

| Goal | Commands |
|------|----------|
| Upgrade to latest | `box pull priv && box set-image priv && box assemble priv` (skip `set-image` if already on `latest`) |
| Rollback | `box set-image priv <tag> && box pull priv <tag> && box assemble priv` |
| Recreate without re-pulling | `box assemble priv` |

## Adding a new command

1. Add a `cmd_<name>()` function (use `_` in the function name for hyphens in the command name, e.g. `cmd_set_image` for `set-image`)
2. Add the case to the dispatch block at the bottom
3. Add it to the `usage()` help text
4. Validate arguments (box name, required args) at the top of the function
