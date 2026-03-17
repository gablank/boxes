# boxes

Distrobox container environments built via GitHub Actions CI and managed locally with the `box` CLI.

Each box is an [Arch Linux](https://archlinux.org/) container with a full development toolchain — zsh, Cursor, VS Code, Docker, Python tooling, and more — shared home directory with the host, and Podman socket passthrough so Docker tooling works inside the box.

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
box init        [owner]         Set image registry owner in all ini files (default: git remote)
box list                        List all boxes with status and image tag
box enter       <box>           Enter a box
box set-image   <box> [tag]     Set the image tag in the ini (default: latest)
box assemble    <box>           Create/recreate box from current ini
box assemble-all                Assemble all boxes
box pull        <box> [tag]     Pull image without rebuilding (default: current tag in ini)
box stop        <box>           Stop a box
box status      <box>           Show detailed box info and build metadata
box logs        <box>           Show init log
box images      <box>           List available image versions on ghcr.io
box completions <bash|zsh|install>  Print or install shell completions
```

**Common workflows:**

| Goal | Commands |
|------|----------|
| Upgrade to latest | `box pull priv && box set-image priv && box assemble priv` (skip `set-image` if already on `latest`) |
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
   box rebuild priv
   box rebuild work
   ```

If you ever need to manually re-point image URLs (e.g. after changing the remote), run:

```bash
box init                        # auto-detect from git remote
box init <github-username>      # or specify explicitly
```

## Customization

### Add a package to all boxes

Edit `Containerfile.base` and add the package to the `pacman -S` block (official packages) or the `yay -S` block (AUR packages):

```dockerfile
RUN pacman -S --noconfirm --needed <package>
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

See [AGENTS.md](AGENTS.md) — the "Adding a New Box" section has step-by-step instructions.

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
dev/
  Containerfile         Thin layer on base for devbox (no init, no root)
  box.toml              Container definition (source of truth)
local-bin/              Scripts installed into ALL boxes
scripts/
  init-user.sh          Runtime user init (runs once on first container start)
bin/
  box                   Host-side CLI
setup.sh                One-shot setup script for new users
.github/workflows/
  build.yml             CI build and cleanup
```
