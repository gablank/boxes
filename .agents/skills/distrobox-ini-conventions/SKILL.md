---
name: distrobox-ini-conventions
description: Conventions for editing distrobox.ini files in this repo. Use when modifying priv/distrobox.ini, work/distrobox.ini, or creating a new box's distrobox.ini.
---

# distrobox.ini Conventions

`distrobox assemble` expands `${VAR}` environment variables at runtime. Always use env vars for anything user- or machine-specific — never hardcode.

## Required env var substitutions

| Field | Use | Not |
|-------|-----|-----|
| `home=` | `${HOME}/distrobox/<box>/home` | `/home/alice/distrobox/...` |
| `volume=` | `${XDG_RUNTIME_DIR}/podman/podman.sock:/podman.sock:rw` | `/run/user/1000/...` |
| `init_hooks=` | `su - ${USER} -c "..."` | `su - alice -c "..."` |

## Template for a new box

The `image=` line is managed by `bin/box init` and `bin/box rebuild`/`revert`. Use a placeholder initially; `box init` will fill in the correct registry owner based on the git remote.

```ini
[<boxname>]
name=<boxname>
image=ghcr.io/gablank/box-<name>:latest
home=${HOME}/distrobox/<boxname>/home
replace=true
pull=true
start_now=true
init=false
volume=${XDG_RUNTIME_DIR}/podman/podman.sock:/podman.sock:rw
pre_init_hooks=export SHELL=/usr/bin/zsh
init_hooks=su - ${USER} -c "bash /usr/local/share/box-init/init-user.sh"
```

The `gablank` in the template is a placeholder/default. After `box init` runs it will be replaced with the actual owner derived from the git remote.

## box rebuild vs box revert

- `box rebuild <box>` — always recreates unconditionally with the latest image.
- `box revert <box> <tag>` — pins to a specific date tag.
