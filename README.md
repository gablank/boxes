# boxes

Distrobox container environments built via GitHub Actions CI and managed locally with the `box` CLI.

Each box is an [Arch Linux](https://archlinux.org/) container with a full development toolchain — zsh, Cursor, VS Code, Docker, Python tooling, and more — with its own persistent home directory (`~/distrobox/<box>/home`). Docker tooling works inside the boxes: `priv` passes through the host podman socket, `work` runs its own rootless podman.

`priv` and `work` also run `sshd`, and their SSH host keys persist in `~/distrobox/<box>/ssh-hostkeys/` so upgrading a box doesn't make clients think its identity changed. Delete that directory and restart the box to rotate the keys deliberately.

## Boxes

| Box | Purpose |
|-----|---------|
| `priv` | Personal development environment |
| `work` | Work environment (adds kubectl, k9s, qemu, glab) |
| `dev` | Minimal box for developing the box system itself |

## Quick Start

### Prerequisites

- [podman](https://podman.io/docs/installation)
- [distrobox](https://distrobox.it/#installation) ≥ 1.7
- Passwordless `sudo` for podman (required for rootful containers):
  ```bash
  sudo EDITOR="tee" visudo -f /etc/sudoers.d/distrobox-rootful <<< "$USER ALL=(ALL) NOPASSWD: /usr/bin/podman"
  ```

### 1. Clone and run setup

```bash
git clone https://github.com/gablank/boxes.git
cd boxes
./setup.sh
```

`setup.sh` will:
- Check that prerequisites are installed
- Add the repo's `bin/` directory to your PATH (writes to `~/.bashrc` / `~/.zshrc`)
- Configure image URLs to match this repo's registry owner
- Install shell completions (bash and zsh)

### 2. Pull and start a box

```bash
box pull priv && box assemble priv
box pull work && box assemble work
```

### 3. Enter a box

```bash
box enter priv
box enter work
```

## The `box` CLI

```
box init        [owner]         Set image registry owner in all box.toml files (default: git remote)
box list                        List all boxes with status and image tag
box enter       <box>           Enter a box
box rescue      <box>           Reassemble without init hooks and enter (stops the box)
box set-image   <box> [tag]     Set the image tag in box.toml (default: latest)
box build       [--no-cache] <box>  Build container image locally (base + box); does not restart
box upgrade     <box>           Set tag to latest, pull, and reassemble (stops the box)
box assemble    [-v] <box>      Create/recreate box from current box.toml (stops the box)
box assemble-all                Assemble all boxes (stops all boxes)
box pull        <box> [tag]     Pull image without rebuilding (default: current tag in box.toml)
box stop        <box>           Stop a box
box status      <box>           Show detailed box info and build metadata
box logs        <box> [...]     Show container logs (pass-through to podman logs)
box images      <box>           List available image versions on ghcr.io
box vendor-aur  <pkgbase>...     Re-vendor AUR PKGBUILDs and show a diff to vet (--all for every one)
box completions <bash|zsh|install>  Print or install shell completions
```

**Common workflows:**

| Goal | Commands |
|------|----------|
| Upgrade to latest | `box upgrade priv` |
| Rollback | `box set-image priv <tag> && box pull priv <tag> && box assemble priv` |
| Recreate without re-pulling | `box assemble priv` |

## Forking / Using Your Own Images

This repo is designed to be forked. When you fork and push to GitHub, CI automatically builds and pushes images to your own GitHub Container Registry (`ghcr.io/<your-username>/box-*`).

**Steps after forking:**

1. Fork this repo on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/<your-username>/boxes.git
   cd boxes
   ./setup.sh
   ```
   `setup.sh` detects your GitHub username from the git remote and calls `box init` to update image URLs automatically.

3. Push to `main` (or wait for the nightly schedule) — GitHub Actions will build and push images to your registry.

4. Pull and start your boxes:
   ```bash
   box pull priv && box assemble priv
   box pull work && box assemble work
   ```

If you ever need to manually re-point image URLs (e.g. after changing the remote), run:

```bash
box init                        # auto-detect from git remote
box init <github-username>      # or specify explicitly
```

## Customization

### Add a package to all boxes

For an **official** package, edit `Containerfile.base` and add it to the `pacman -S` block:

```dockerfile
RUN pacman -S --noconfirm --needed <package>
```

For an **AUR** package, the build never fetches from the AUR — it builds only from
vetted PKGBUILDs vendored under `aur/` (a supply-chain control; see `aur/README.md`).
Vendor and review the new package, then add a `makepkg` step to the AUR section of
`Containerfile.base`:

```bash
box vendor-aur <pkgbase>   # clones from the AUR, prints a diff to vet
# review the diff, then: git add aur/ && git commit
```

### Add a package to one box

Edit that box's `Containerfile` (`priv/Containerfile` or `work/Containerfile`).

### Add a Cursor extension

Add the extension ID to the extension install loop in `Containerfile.base`:

```dockerfile
for ext in \
    ...
    publisher.extension-name; \
do \
```

### Add a new box

See [AGENTS.md](AGENTS.md) — the "Adding or Removing a Box" section points at the step-by-step checklist in `.agents/skills/adding-a-box/SKILL.md`.

## Image Build

Images are built by GitHub Actions on every push to `main` and nightly at 03:00 UTC. Builds are skipped when the relevant files haven't changed — base only rebuilds if `Containerfile.base`, `scripts/`, or `local-bin/` changed; each box only rebuilds if base or its own directory changed. Scheduled and manual runs always rebuild everything.

- `ghcr.io/<owner>/box-base` — base image with all shared packages
- `ghcr.io/<owner>/box-priv` — privbox image
- `ghcr.io/<owner>/box-work` — workbox image
- `ghcr.io/<owner>/box-dev` — devbox image

Each image is tagged `latest` and `YYYY-MM-DDTHHMM` (UTC, e.g. `2026-03-04T0300`). Images older than 14 days are automatically deleted (keeping `latest`).

## Repository Structure

```
Containerfile.base      Shared base image
priv/
  Containerfile         Thin layer on base for privbox
  box.toml              Container definition (source of truth)
  local-bin/            Scripts installed only into privbox
work/
  Containerfile         Thin layer on base for workbox
  box.toml              Container definition (source of truth)
  local-bin/            Scripts installed only into workbox
  systemd-user/         User units installed only into workbox
dev/
  Containerfile         Thin layer on base for devbox (no init, no root)
  box.toml              Container definition (source of truth)
local-bin/              Scripts installed into ALL boxes
scripts/
  init-root.sh          First-start root init (chsh, /etc/environment)
  init-user.sh          First-start user init (~/.ssh, .zshrc, rustup)
  shell-init.sh         Sourced from .zshrc on every shell open
  compile-box-toml.py   Compiles box.toml → distrobox.ini
bin/
  box                   Host-side CLI
setup.sh                One-shot setup script for new users
.github/workflows/
  build.yml             CI build and cleanup
```
