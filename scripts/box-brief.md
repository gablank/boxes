# You are running inside a distrobox container

The shell you have is an Arch Linux **distrobox** container on an immutable
Fedora host (Bazzite/Aurora), not the host itself. A few assumptions that hold
on a normal machine do not hold here.

- **The container is disposable; only `$HOME` survives.** Every box is created
  with `replace = true`, so `box upgrade` / `box assemble` destroys and
  recreates it from a published image. Anything installed with `pacman`/`yay`,
  and any edit to a packaged file under `/etc` or `/usr`, is silently reverted
  on the next recreate — it keeps working until then, so the loss surfaces far
  from the cause.

- **Persistent changes belong in the `boxes` repo**, which builds these images
  (`Containerfile.base` for all boxes, `<box>/Containerfile` for one). Installing
  a tool means a PR there, not `pacman -S`. If you need a package that is not
  present, say so rather than installing it — a `pacman -S` that "works" is a
  change that disappears.

- **Each box has a different `$HOME`**, mounted from the host at
  `~/distrobox/<box>/home`. `/tmp` is shared between the host and *every* box.
  `$CONTAINER_ID` (and the prompt badge) tells you which box you are in.

- **The host filesystem is read-only at `/run/host`.** To run a command on the
  host, use `distrobox-host-exec <cmd>`. Container management — `distrobox`,
  the host's `podman`, and `box assemble|pull|enter|list|upgrade` — cannot run
  from inside a box; ask the user to run those on the host.

- **USB and HID devices are not visible here.** Smartcard/YubiKey *CCID* applets
  work through the host's `pcscd` (`ykman info|piv|oath|openpgp`,
  `gpg --card-status`, PIV-backed SSH, `age-plugin-yubikey`), but anything that
  opens `/dev/hidraw*` — FIDO2/WebAuthn, `ssh-keygen -t ed25519-sk`,
  `ykman otp|fido` — must be run on the host.
