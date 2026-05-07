---
name: box-toml-conventions
description: Conventions for editing box.toml files in this repo. Use when modifying priv/box.toml, work/box.toml, dev/box.toml, or creating a new box's box.toml.
---

# box.toml Conventions

`box.toml` is the source of truth for each box. `scripts/compile-box-toml.py` compiles it to `distrobox.ini` (gitignored, regenerated on every `box assemble`/`box set-image`/`box init`). **Never edit `distrobox.ini` directly.**

`distrobox assemble` expands `${VAR}` host-side env vars at runtime. Always use env vars for anything user- or machine-specific — never hardcode.

## Required env var substitutions

| Field | Use | Not |
|-------|-----|-----|
| `home = ` | `"${HOME}/distrobox/<box>/home"` | `"/home/alice/distrobox/..."` |
| `[[mount-file]]` host (sockets) | `"${XDG_RUNTIME_DIR}/podman/podman.sock"` | `"/run/user/1000/..."` |
| `init_hooks = ` | `su - ${container_user_name} -c "..."` | `su - ${USER} -c "..."` or `su - alice -c "..."` |

### Why `${container_user_name}` and not `${USER}`

`init_hooks` are evaluated inside the container by `distrobox-init` via `eval ${init_hook}`. At that point `/etc/profile.d/distrobox_profile.sh` has not been sourced, so `USER` is **unbound** (triggering `set -u` errors). `container_user_name` is a shell variable set by `distrobox-init` before the eval and is guaranteed to be in scope.

## Mounts

| Section | Compiles to | Use for |
|---------|-------------|---------|
| `[[mount-dir]]` | `volume=` line | Directories. **Auto-created on host** by `box assemble` if missing. |
| `[[mount-file]]` | `--volume` flag in `additional_flags` | Sockets, files. **Must already exist on host** at assemble time. |

Each entry has `host`, `container`, and optional `options` (e.g. `"rw,z"`). The `:z` SELinux relabel suffix is required on SELinux-enforcing hosts (Bazzite/Fedora).

## Init script execution contexts

`init_hooks` runs three scripts in sequence. Each runs in a different context — putting code in the wrong script will fail silently or crash the assemble.

| Script | Runs as | TTY | When | Use for |
|--------|---------|-----|------|---------|
| `init-root.sh` | root | No | First container start, from `init_hooks` before `su` | `chsh`, writing `/etc/environment`, systemd overrides — anything requiring root |
| `init-user.sh` | container user | No | First container start, from `init_hooks` via `su -` | User dotfiles, `~/.ssh`, `.zshrc` setup — anything in `$HOME` |
| `shell-init.sh` | container user | Yes | Every interactive shell open (sourced from `.zshrc`) | Runtime env vars, aliases, service health checks |

**Critical constraint:** `init-root.sh` and `init-user.sh` have **no TTY**. Commands that prompt for input (`sudo`, interactive `chsh`, `passwd`) will fail. If a command needs root privileges, it belongs in `init-root.sh` (which already runs as root), not in `init-user.sh` with `sudo`.

The `init_hooks` line in `box.toml` chains them:
```toml
init_hooks = '... && bash /usr/local/share/box-init/init-root.sh ${container_user_name} && su - ${container_user_name} -c "bash /usr/local/share/box-init/init-user.sh"'
```

## Template for a new box

The `image = ` line is managed by `bin/box init` and `bin/box set-image`. Use a placeholder initially; `box init` will fill in the correct registry owner based on the git remote.

```toml
[distrobox]
name = "<boxname>"
image = "ghcr.io/gablank/box-<name>:latest"
home = "${HOME}/distrobox/<boxname>/home"
replace = true
pull = true
start_now = true
init = false
additional_flags = "--security-opt seccomp=unconfined"
pre_init_hooks = "export SHELL=/usr/bin/zsh"
init_hooks = 'bash /usr/local/share/box-init/init-root.sh ${container_user_name} && su - ${container_user_name} -c "bash /usr/local/share/box-init/init-user.sh"'

[[mount-file]]
host = "${XDG_RUNTIME_DIR}/podman/podman.sock"
container = "/podman.sock"
options = "rw"
```

The `gablank` in the template is a placeholder/default. After `box init` runs it will be replaced with the actual owner derived from the git remote.

## Tailscale per box

Each box can have its own tailscale node (connecting to a different tailnet) using `unshare_netns = true`. With a private network namespace, the box's user namespace owns that netns, making `CAP_NET_ADMIN` valid for `TUNSETIFF` (TUN device creation).

The base image solves the host-socket-shadowing problem (distrobox-init symlinks `/var/run/tailscale/tailscaled.sock` to the host's daemon) **at build time**, not via init_hooks:

- A systemd drop-in (`/etc/systemd/system/tailscaled.service.d/socket-path.conf`) launches `tailscaled` with `--socket=/var/run/tailscale/box.sock`, sidestepping the host symlink entirely.
- `/usr/bin/tailscale` is replaced with a wrapper that injects `--socket=/var/run/tailscale/box.sock` for every call. The original binary is preserved as `/usr/bin/tailscale.real`.
- `IgnorePkg = tailscale` in `/etc/pacman.conf` keeps in-container `pacman -Syu` from overwriting the wrapper. Image rebuilds reinstall fresh and re-apply.

See `Containerfile.base` for the wrapper definition. **Per-box `box.toml` only needs**:

```toml
unshare_netns = true
additional_flags = "--security-opt seccomp=unconfined --device /dev/net/tun --cap-add NET_ADMIN --cap-add NET_RAW"

[[mount-dir]]
host = "${HOME}/distrobox/<box>/tailscale"
container = "/var/lib/tailscale"
options = "rw,z"
```

No init_hooks tweaks, no shell-init logic — the systemd unit and wrapper handle it. After first `box assemble <box>`, run `tailscale up` inside the box to authenticate; auth state persists in `~/distrobox/<box>/tailscale/`.

### Docker-compose services on the box tailnet

To make compose services share the box's network namespace (reachable via `localhost` and on the box's tailnet):

```yaml
services:
  myservice:
    network_mode: "container:workbox"
```

Port collisions between services must be avoided manually since they all share one netns. Inter-service communication uses `localhost:PORT` rather than Docker service DNS.

## Common workflows (CLI reference)

| Goal | Commands |
|------|----------|
| Upgrade to latest | `box pull <box> && box set-image <box> && box assemble <box>` (skip `set-image` if already on `latest`) |
| Rollback | `box set-image <box> <tag> && box pull <box> <tag> && box assemble <box>` |
| Recreate without re-pulling | `box assemble <box>` |
