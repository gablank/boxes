---
name: distrobox-ini-conventions
description: Conventions for editing distrobox.ini files in this repo. Use when modifying priv/distrobox.ini, work/distrobox.ini, or creating a new box's distrobox.ini.
---

# distrobox.ini Conventions

`distrobox assemble` expands `${VAR}` environment variables at runtime for host-side fields. Always use env vars for anything user- or machine-specific — never hardcode.

## Required env var substitutions

| Field | Use | Not |
|-------|-----|-----|
| `home=` | `${HOME}/distrobox/<box>/home` | `/home/alice/distrobox/...` |
| `volume=` | `${XDG_RUNTIME_DIR}/podman/podman.sock:/podman.sock:rw` | `/run/user/1000/...` |
| `init_hooks=` | `su - ${container_user_name} -c "..."` | `su - ${USER} -c "..."` or `su - alice -c "..."` |

### Why `${container_user_name}` and not `${USER}`

`init_hooks` are evaluated inside the container by `distrobox-init` via `eval ${init_hook}`. At that point `/etc/profile.d/distrobox_profile.sh` has not been sourced, so `USER` is **unbound** (triggering `set -u` errors). `container_user_name` is a shell variable set by `distrobox-init` before the eval and is guaranteed to be in scope.

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
additional_flags=--security-opt seccomp=unconfined
volume=${XDG_RUNTIME_DIR}/podman/podman.sock:/podman.sock:rw
pre_init_hooks=export SHELL=/usr/bin/zsh
init_hooks=su - ${container_user_name} -c "bash /usr/local/share/box-init/init-user.sh"
```

The `gablank` in the template is a placeholder/default. After `box init` runs it will be replaced with the actual owner derived from the git remote.

## Tailscale per box

To run a separate Tailscale daemon inside a box (persisting auth state across recreates):

```ini
volume=${HOME}/distrobox/<box>/tailscale:/var/lib/tailscale:rw,z
additional_flags=--security-opt seccomp=unconfined --device /dev/net/tun --cap-add NET_ADMIN --cap-add NET_RAW
init_hooks=su - ${container_user_name} -c "bash /usr/local/share/box-init/init-user.sh" && tailscaled --statedir=/var/lib/tailscale &
```

- The `:z` on the volume mount is required on SELinux-enforcing hosts (Bazzite/Fedora)
- `init_hooks` starts tailscaled on container creation; `init-user.sh` adds a `.zshrc` snippet that auto-restarts it on shell open (covers the host-reboot case)
- After first assemble run `tailscale up` inside the box; auth state persists in the host directory

## box rebuild vs box revert

- `box rebuild <box>` — always recreates unconditionally with the latest image.
- `box revert <box> <tag>` — pins to a specific date tag.
