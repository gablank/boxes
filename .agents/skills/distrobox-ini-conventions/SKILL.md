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

Each box can have its own tailscale node (connecting to a different tailnet) using `unshare_netns=true`. With a private network namespace, the box's user namespace owns that netns, making `CAP_NET_ADMIN` valid for `TUNSETIFF` (TUN device creation).

Distrobox-init always creates `/var/run/tailscale/tailscaled.sock` as a symlink to the host's socket. To avoid the box's tailscaled colliding with that, use a separate socket path.

Add to `distrobox.ini`:

```ini
unshare_netns=true
volume=${HOME}/distrobox/<box>/tailscale:/var/lib/tailscale:rw,z
additional_flags=--security-opt seccomp=unconfined --device /dev/net/tun --cap-add NET_ADMIN --cap-add NET_RAW
init_hooks=su - ${container_user_name} -c "bash /usr/local/share/box-init/init-user.sh" && mkdir -p /var/run/tailscale-box && tailscaled --statedir=/var/lib/tailscale --socket=/var/run/tailscale-box/tailscaled.sock &
```

- The `:z` on the volume mount is required on SELinux-enforcing hosts (Bazzite/Fedora)
- `init-user.sh` detects `/var/lib/tailscale` and sets `TS_SOCKET=/var/run/tailscale-box/tailscaled.sock` in `.zshenv`, and adds a `.zshrc` snippet that auto-restarts tailscaled on shell open if the socket is missing (covers host reboots)
- After first `box assemble <box>`, run `tailscale up` inside the box to authenticate; auth state persists in `~/distrobox/<box>/tailscale/`

### Docker-compose services on the box tailnet

To make compose services share the box's network namespace (reachable via `localhost` and on the box's tailnet):

```yaml
services:
  myservice:
    network_mode: "container:workbox"
```

Port collisions between services must be avoided manually since they all share one netns. Inter-service communication uses `localhost:PORT` rather than Docker service DNS.

## box rebuild vs box revert

- `box rebuild <box>` — always recreates unconditionally with the latest image.
- `box revert <box> <tag>` — pins to a specific date tag.
