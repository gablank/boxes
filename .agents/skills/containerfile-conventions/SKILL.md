---
name: containerfile-conventions
description: Conventions for editing Containerfiles in this repo. Use when modifying Containerfile.base, priv/Containerfile, work/Containerfile, adding packages, or adding Cursor extensions.
---

# Containerfile Conventions

## Base image (`Containerfile.base`)

- Starts from `archlinux:latest`
- The bootstrap-package reinstall (`pacman -Qqn | pacman -S --overwrite '*' -`, which restores man pages stripped by the bootstrap image) runs immediately after the first layer, **before any customization**. Never add a blanket package reinstall later in the file — it re-extracts package files over earlier layer modifications (this once silently overwrote the tailscale wrapper).
- Installs shared packages used by ALL boxes (pacman and AUR)
- Creates a temporary `builduser` for makepkg/yay, removes it at the end
- Pre-installs Cursor extensions to `/opt/cursor-extensions/`
- COPYs `scripts/init-user.sh` and `local-bin/` into the image
- Writes `/etc/box-build-info` using `BUILD_DATE` and `BUILD_SHA` build args
- Clean up caches at the end (`pacman -Scc --noconfirm`, `rm -rf /var/cache/pacman/pkg/*`)

## Box-specific Containerfiles

- Declare `ARG BASE_IMAGE=ghcr.io/gablank/box-base:latest` followed by `FROM ${BASE_IMAGE}`. CI passes the correct fork owner's registry via this build arg.
- Add only packages unique to that box
- COPY `{box}/local-bin/` for box-specific scripts
- Overwrite `/etc/box-build-info` with the box-specific image name
- Build context is the repo root (not the box subdirectory)

## Workbox rootless podman (podman-in-podman)

`work/Containerfile` carries two pieces of glue for the box-local rootless podman; keep both when touching it:

- `containers.conf.d/10-box-rootless.conf` — `cgroup_manager = "cgroupfs"` and `events_logger = "file"`, because the user systemd manager inside distrobox has no cgroup delegation and no user journal.
- `work/systemd-user/podman-graceful-shutdown.service` (COPY'd to `/etc/systemd/user/` and enabled via a `default.target.wants` symlink, since `systemctl --global enable` needs a running systemd) — runs `podman stop --all` from `ExecStop` so inner containers exit cleanly when the box stops. Without it, box shutdown SIGKILLs conmon before exits are recorded and containers reappear Dead/stuck after restart. Inner podman's RunRoot (`/run/user/UID/containers`) is on the box's own `/run` tmpfs (init boxes get a fresh `/run`; distrobox only binds the host's `/run/user/UID` into init=0 boxes), so reboot detection itself works — unclean shutdown was the problem.

## Adding a new package

- All boxes: add to `Containerfile.base` (pacman: `pacman -S --noconfirm --needed <pkg>`, AUR: `yay -S --noconfirm --needed <pkg>` as builduser)
- One box: add to that box's Containerfile

## Adding a new Cursor extension

Add it to the extension install loop in `Containerfile.base`.
