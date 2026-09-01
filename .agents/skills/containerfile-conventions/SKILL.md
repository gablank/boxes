---
name: containerfile-conventions
description: Conventions for editing Containerfiles in this repo. Use when modifying Containerfile.base, priv/Containerfile, work/Containerfile, adding packages, or adding Cursor extensions.
---

# Containerfile Conventions

## Base image (`Containerfile.base`)

- Starts from `archlinux:latest`
- The bootstrap-package reinstall (`pacman -Qqn | pacman -S --overwrite '*' -`, which restores man pages stripped by the bootstrap image) runs immediately after the first layer, **before any customization**. Never add a blanket package reinstall later in the file — it re-extracts package files over earlier layer modifications (this once silently overwrote the tailscale wrapper).
- Installs shared packages used by ALL boxes: pacman packages, plus AUR packages built with `makepkg` from the vetted PKGBUILDs vendored in `aur/` (never `yay -S`/`git clone` from the AUR — supply-chain control; see `aur/README.md`). `yay` itself is vendored and built here so it still ships for interactive use.
- Creates a temporary `builduser` for makepkg, removes it at the end
- Enables `sshd` and redirects its `HostKey` paths to `/var/lib/box-ssh` (drop-in + `box-sshd-keygen` `ExecStartPre`) so host keys outlive container recreates. Host keys are generated at runtime, never baked into the image — the repo is public. Init boxes must pair this with the `ssh-hostkeys` `[[mount-dir]]`; see `.agents/skills/box-toml-conventions/SKILL.md`.
- **sshd settings go in `/etc/ssh/sshd_config.d/*.conf` from this file, never as an edit to `/etc/ssh/sshd_config`** — that path is in the writable layer and every recreate reverts it to the packaged default, so a hardened setting silently un-hardens. `10-box-auth.conf` enforces key-only auth (`PasswordAuthentication no` **and** `KbdInteractiveAuthentication no` — with `UsePAM yes`, keyboard-interactive would otherwise still accept the password, and `priv`/`work` import the host's shadow hash). Keep the `10-` prefix: sshd takes the first value obtained for a keyword and the main config `Include`s the dir on line 2, so `10-` beats Arch's `99-archlinux.conf`. See the matching bullet in `AGENTS.md`.
- Installs the smartcard/YubiKey client stack (`yubikey-manager`, `libfido2`, `opensc`, `yubico-piv-tool`, `pcsc-tools`, plus `age` + `age-plugin-yubikey`, whose identities live on the PIV applet; `pcsclite` + `ccid` arrive as deps) and **masks `pcscd.service` and `pcscd.socket`**. The daemon runs on the host: distrobox forwards `/run/pcscd/pcscd.comm` in as a symlink to it (same mechanism as the tailscale socket shadowing), and an in-box pcscd could not work anyway because podman gives each container a minimal `/dev` with no `/dev/bus/usb`. **Never enable those units** — the Arch wiki's `enable pcscd.service` step does not apply here. CCID paths (`ykman info|piv|oath|openpgp`, PKCS#11 SSH, `gpg --card-status`, `age-plugin-yubikey`) can work in a box; HID paths (`fido2-token`, `ssh-keygen -t ed25519-sk`, `ykman otp|fido`, Chrome WebAuthn) need `/dev/hidraw*` and must run on the host until a box passes USB devices through.
- The CCID path is additionally polkit-gated on the host, and that gate is **not** configured from this repo. pcscd allows `access_pcsc`/`access_card` on `allow_active` only: rootless `dev` sits under `user@1000.service` and resolves to the user's session (allowed), rootful `priv`/`work` sit under `machine.slice` with no session (denied, reported as `SCARD_W_SECURITY_VIOLATION` / `WARNING: PC/SC not available`). `README.md` documents the opt-in host polkit rule; keep it host-side. See the matching bullet in `AGENTS.md` for the `pkcheck` proof command and the two diagnosis traps (sandboxed AF_UNIX, container PID namespace).
- Installs `host-spawn` to `/usr/bin/host-spawn` from a version-pinned, sha256-checked upstream GitHub release — it is in neither the official repos nor the AUR, so this is the one download in the file that isn't `pacman`/`makepkg`; keep the checksum pin. distrobox requires it (`/etc/profile.d/distrobox_profile.sh` on every login shell, and `distrobox-host-exec`) but bind-mounts only its own shell scripts and no binary. Its fallback is a silent best-effort download during `distrobox-init`, into the writable layer that every `replace=true` recreate discards; it lands in `dev` but not in `priv`/`work` (suspected: no egress at init time inside their own netns, `unshare_netns = true`). **Contract:** the pinned version must be >= the `host_spawn_version` that the host's `distrobox-host-exec` requires, or that prompt returns. The binary dispatches on its own `argv[0]`, so it must keep the name `host-spawn` — a differently named symlink to it runs *that* command on the host.
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

- All boxes, official: add to `Containerfile.base` `pacman -S --noconfirm --needed <pkg>`
- All boxes, AUR: **never** add a `yay -S` line. Vendor + vet the PKGBUILD first (`box vendor-aur <pkgbase>`, review the diff, commit `aur/`), then add a `makepkg` build step to the AUR section of `Containerfile.base`. Split pkgbases follow the `google-cloud-cli` pattern (build once, `pacman -U` only the wanted outputs). See `aur/README.md`.
- One box: add to that box's Containerfile (official deps only; AUR uses the vendored flow above)

## Adding a new Cursor extension

Add it to the extension install loop in `Containerfile.base`.
