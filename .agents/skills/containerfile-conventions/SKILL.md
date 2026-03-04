---
name: containerfile-conventions
description: Conventions for editing Containerfiles in this repo. Use when modifying Containerfile.base, priv/Containerfile, work/Containerfile, adding packages, or adding Cursor extensions.
---

# Containerfile Conventions

## Base image (`Containerfile.base`)

- Starts from `archlinux:latest`
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

## Adding a new package

- All boxes: add to `Containerfile.base` (pacman: `pacman -S --noconfirm --needed <pkg>`, AUR: `yay -S --noconfirm --needed <pkg>` as builduser)
- One box: add to that box's Containerfile

## Adding a new Cursor extension

Add it to the extension install loop in `Containerfile.base`.
