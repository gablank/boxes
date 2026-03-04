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

## box stage vs box rebuild

- `box stage <box>` — pulls latest image; recreates only if the image digest changed. Use for routine updates.
- `box rebuild <box>` — always recreates unconditionally. Use to force a clean container.
- `box revert <box> <tag>` — pins to a specific date tag.
