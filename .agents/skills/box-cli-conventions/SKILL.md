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

## Image tag management

- `box rebuild` always resets the `image=` line to `:latest`
- `box revert` pins to a specific `:YYYY-MM-DDTHHMM` tag (e.g. `2026-03-04T0300`); old `YYYY-MM-DD` tags are still supported
- `box images <box>` lists available tags with a human-readable age column (uses `time_ago()`)
- The `image=` line in distrobox.ini is managed by the tool; manual edits are fine but will be overwritten on next rebuild/revert

## Adding a new command

1. Add a `cmd_<name>()` function
2. Add the case to the dispatch block at the bottom
3. Add it to the `usage()` help text
4. Validate arguments (box name, required args) at the top of the function
