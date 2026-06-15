---
name: box-cli-conventions
description: Conventions for the bin/box CLI tool. Use when modifying bin/box, adding commands, or changing how box management works.
---

# bin/box CLI Conventions

## Design principles

- Pure bash, no external dependencies beyond `distrobox`, `curl`, `git` (for `vendor-aur`), Python 3.11+ (for the box.toml compiler), and standard coreutils; no `gh` CLI required
- Resolves repo root from its own location so it works from any working directory
- Auto-discovers boxes by scanning for `*/box.toml` in the repo root
- The box argument is always the directory name (`priv`, `work`), not the container name (`privbox`, `workbox`)
- `box.toml` is the source of truth; commands that mutate config (`init`, `set-image`) edit the toml and recompile to `distrobox.ini` via `scripts/compile-box-toml.py`

## Command responsibilities

Each command has exactly one responsibility:

- `set-image <box> [tag]` — updates `image = ` in `box.toml` and recompiles (default: `latest`); no pull, no assemble
- `assemble <box>` — recompiles `box.toml` → `distrobox.ini` and runs `distrobox assemble create`; no image tag manipulation
- `assemble-all` — calls `assemble` for each discovered box
- `pull <box> [tag]` — `podman pull`; no toml change, no assemble
- `upgrade <box>` — the one composite command: sets the tag to `latest`, then calls `pull` and `assemble`
- `build [--no-cache] <box>` — local image build (base + box); uses the layer cache unless `--no-cache` is given
- `images <box>` — lists registry tags; marks the tag the container is built from with `← current` (green), and the tag the next `assemble` will use with `← next` (yellow); `← current` uses `podman inspect` so it appears on stopped containers too
- `vendor-aur <pkgbase>... | --all` — re-vendors AUR PKGBUILDs into `aur/` and prints a diff to vet (thin wrapper over `scripts/vendor-aur.sh`); takes a pkgbase, **not** a box, so it is not in `_BOX_COMMANDS_WITH_BOX`

## Image tag management

- The `image = ` line in `box.toml` is managed by `set-image`, `upgrade`, `init`, and `build` (which pins the freshly built `local-` tag); manual edits to `box.toml` are fine (re-run `box assemble` to regenerate the ini), but never hand-edit `distrobox.ini`
- Old `YYYY-MM-DD` tags are still supported by `time_ago()` alongside the current `YYYY-MM-DDTHHMM` format
- `images` uses `_image_markers()` (private helper, prefixed `_`) to annotate tags; it reads the tag from `box.toml`

## Common workflows

| Goal | Commands |
|------|----------|
| Upgrade to latest | `box upgrade priv` |
| Rollback | `box set-image priv <tag> && box pull priv <tag> && box assemble priv` |
| Recreate without re-pulling | `box assemble priv` |

## Shell completions

Completions are embedded in `bin/box` and output by `box completions bash` / `box completions zsh`. `setup.sh` installs them by appending `eval "$(box completions <shell>)"` to `~/.bashrc` / `~/.zshrc`. Because the eval runs at shell startup, completions always reflect the current `bin/box` after a `git pull` — no manual reinstall needed.

**Single source of truth:** `_BOX_COMMANDS` (all commands) and `_BOX_COMMANDS_WITH_BOX` (commands whose first arg is a box) at the top of `bin/box`. The completion heredocs do **not** hardcode command lists — they carry `@@CMDS@@` / `@@BOX_CMDS@@` placeholders that `_completions_bash`/`_completions_zsh` substitute from those arrays via `sed`. Keep the arrays correct and the completions follow automatically. The CI `lint` job verifies the case dispatch matches `_BOX_COMMANDS` and that both completions contain every command.

## Adding a new command

1. Add a `cmd_<name>()` function (use `_` in the function name for hyphens in the command name, e.g. `cmd_set_image` for `set-image`)
2. Add the case to the dispatch block at the bottom
3. Add it to the `usage()` help text
4. Validate arguments (box name, required args) at the top of the function
5. **Add the command name to `_BOX_COMMANDS`** — CI will fail if this is missing
6. If the command takes `<box>` as its first arg, also add it to `_BOX_COMMANDS_WITH_BOX` (both arrays drive the completion heredocs via placeholder substitution — no hand-editing of command lists in the heredocs)
7. Add a description line to the zsh `_box_commands()` helper inside `_completions_zsh()` (the only manually maintained completion text)
