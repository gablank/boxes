# Agent Guidelines

This file provides instructions for AI coding agents working on this repository.

## Keeping Agent Documentation Up to Date — BLOCKING

Documentation drift is the #1 maintenance failure in this repo. **Every code change MUST be accompanied by a documentation audit.** A task is not complete until docs are in sync.

The full protocol — what to check before starting, the per-file audit checklist, and the "removing a workaround" greppable-cleanup rule — lives in `.agents/rules/core.mdc` and is loaded automatically (alwaysApply). Read it. The short version:

- **Before** changing code, read the docs that describe the area you're about to change.
- **After** changing code, walk the per-file checklist in `core.mdc` and update every affected doc surface (`README.md`, `AGENTS.md`, the relevant `.agents/skills/*/SKILL.md`).
- When **removing** a workaround/alias/feature, `grep -rn` the repo for stale references and delete them all.

Outdated docs are worse than no docs.

## Proactive Self-Improvement

Beyond keeping docs in sync, agents must **proactively** improve this repository and its agent files:

- If a skill, rule, or section of `AGENTS.md` is missing or stale — fix it, even if it wasn't part of the current task.
- After completing any task, look for automation opportunities: a missing `bin/box` command, a useful CI job, a script that belongs in `local-bin/`. Mention these to the user explicitly.
- If you performed a manual multi-step process, suggest how to automate it.

This is enforced by `.agents/rules/self-improve.mdc`.

## Agent File Layout

`.agents/` is the canonical home for agent files: `.agents/rules/*.mdc` (always-active rules) and `.agents/skills/*/SKILL.md` (topic skills). `.cursor/rules` and `.cursor/skills` are **symlinks** into `.agents/` so Cursor picks them up — never create real files under `.cursor/`, and edit only the `.agents/` side. `CLAUDE.md` imports `AGENTS.md` for the same reason. Because not every harness auto-loads the skills, `AGENTS.md` intentionally duplicates their key points in summary form — when either side changes, sync the other (see the audit table in `.agents/rules/core.mdc`).

## Development Environment

Work on this repo usually happens **inside the dev box**, where `distrobox` and host `podman` are not available. From there you can edit, run `shellcheck`, compile box.tomls, and mirror every CI lint check — but `box assemble`/`pull`/`enter`/`list` and anything else touching containers must be run by the user on the host. If those commands fail inside a box, that is the environment, not a code bug.

## Workarounds & Known Gotchas

There is currently **one** active workaround needing a per-conversation check (below). This section also records resolved ones so a recurrence is recognised fast.

**`TMUX_TMPDIR` bootstrap blocks outside the repo — DELETE once every box runs the new base image (added 2026-08-20):** the canonical mechanism is `scripts/shell-env.sh`, hooked into `/etc/zsh/zshenv` by `Containerfile.base`. That only exists after a base rebuild + `box upgrade`, so until then the setting is carried by hand-written blocks in four files outside this repo — `~/.zshenv` in each of `~/distrobox/{devbox,privbox,workbox}/home`, and `~/.bashrc` on the host. They are marked `# --- boxes: per-box tmux server`. **Trigger to clean up:** after `box upgrade`, run `grep -c TMUX_TMPDIR /etc/zsh/zshenv` inside a box — if that is 1, the image carries it and all four blocks are dead weight; delete them. Leaving them is harmless (same value, set twice) but they will silently drift from `shell-env.sh`, which is the failure this section exists to prevent. Verify with a fresh `zsh -c 'echo $TMUX_TMPDIR'` in each box afterwards.

**distrobox-enter `--pty` patch — REMOVED, do NOT re-apply (resolved 2026-06-04):** From 2026-04-17 the host carried a patched `~/.local/bin/distrobox-enter` that stripped `--pty` from the su block, working around distrobox issue [#2011](https://github.com/89luca89/distrobox/issues/2011) (PR [#2053](https://github.com/89luca89/distrobox/pull/2053)) where `su --pty` killed the shell on Ctrl+C. **That upstream bug is now fixed, and the patch became the cause of a new breakage.** On rootful + init boxes (`priv`, `work`), distrobox switches user via `su` over a `podman exec -t` pty; `--pty` is what gives that shell its *controlling terminal*. With #2011 fixed, stripping `--pty` no longer helped Ctrl+C and instead dropped the controlling terminal — so `Ctrl+C` printed `Session terminated, killing shell...`, `Ctrl+R` failed with `failed to open /dev/tty`, and `sudo` fell back to the host's leaked `ksshaskpass`. Removing the patch (letting stock `distrobox-enter` pass `--pty`) restored all three. Rootless/no-init `dev` never takes the su path, which is why it was unaffected, and entering the same box via `ssh` or `podman exec -it` always worked (both give a real pty). **The patch must stay removed on every host (Bazzite, Aurora, …).** If a rootful box ever again kills the shell on Ctrl+C or breaks Ctrl+R/sudo, first check whether this obsolete `--pty` patch got re-applied — removing it is the fix. Only re-introduce a `--pty` workaround if upstream #2011 actually regresses.

## PUBLIC REPOSITORY -- READ THIS FIRST

This repository is **public on GitHub**. Every file is visible to the entire internet.

- **NEVER** add secrets, tokens, API keys, passwords, or credentials of any kind
- **NEVER** add personal data: email addresses, phone numbers, private IPs, internal hostnames
- **NEVER** add private SSH keys, GPG keys, or certificates
- **NEVER** hardcode authentication tokens for any service

If something needs a secret at runtime, use environment variables. Document the required env var and read it at runtime -- never bake it into images or check it into the repo.

## Repository Structure

This repo defines distrobox container environments built via CI and managed locally with `bin/box`.

```
Containerfile.base          Shared base image (Arch Linux + pacman + vendored AUR builds + Cursor extensions)
aur/                        Vetted AUR PKGBUILDs vendored per pkgbase; images build only from these (see aur/README.md)
  manifest.tsv              pkgbase → upstream git commit + fetch date (provenance)
  <pkgbase>/                PKGBUILD + local source files (*.install, *.sh, *.patch)
priv/
  Containerfile             Thin layer on base for privbox
  box.toml                  Container definition — source of truth (distrobox.ini is generated, gitignored)
  local-bin/                Scripts/binaries installed only into privbox
work/
  Containerfile             Thin layer on base for workbox (adds kubectl, k9s, qemu, glab, rootless podman)
  box.toml                  Container definition — source of truth
  local-bin/                Scripts/binaries installed only into workbox
  systemd-user/             User units installed only into workbox (podman graceful shutdown)
dev/
  Containerfile             Thin layer on base for devbox (no init, no root — for developing box itself)
  box.toml                  Container definition — source of truth
local-bin/                  Scripts/binaries installed into ALL boxes
scripts/
  init-root.sh              First-start root init (chsh, /etc/environment) — no TTY
  init-user.sh              First-start user init (~/.ssh, .zshrc, rustup) — no TTY, no sudo
  shell-init.sh             Sourced from .zshrc on every shell open — interactive runtime env, services
  shell-env.sh              Sourced from /etc/zsh/zshenv + /etc/profile.d — env every shell needs, interactive or not
  compile-box-toml.py       Compiles box.toml → distrobox.ini (Python 3.11+, stdlib tomllib)
  vendor-aur.sh             Re-vendor AUR PKGBUILDs into aur/ with a diff to vet (box vendor-aur)
bin/
  box                       Host-side CLI for managing boxes
setup.sh                    One-shot setup script for new users / forks
.github/workflows/
  build.yml                 Nightly + on-push CI build and image cleanup
.agents/
  rules/                    Always-active agent rules (core.mdc, self-improve.mdc)
  skills/                   Topic skills, one SKILL.md per topic
.cursor/                    rules + skills symlinks into .agents/ (for Cursor)
```

## Image Build Flow

1. A `changes` job detects which paths changed and computes the `date_tag`; on `schedule`/`workflow_dispatch` all flags are forced true
2. `build-base` runs only if `Containerfile.base`, `scripts/`, or `local-bin/` changed
3. `build-boxes` builds the affected boxes in parallel via a dynamic matrix (after `build-base`); a box is included only if base changed OR its own directory changed
4. All images are tagged `latest` + `YYYY-MM-DDTHHMM` (e.g. `2026-03-04T0300`, UTC) and pushed to ghcr.io
5. Locally, `box upgrade <name>` pulls the latest image and recreates the container

`<repo-owner>` is derived from `github.repository_owner` in CI — no hardcoding, so forks work out of the box.

## Containerfile Conventions

- `Containerfile.base` installs everything shared: pacman packages, AUR packages built from the vetted PKGBUILDs vendored in `aur/` (including `yay` itself, so it ships for interactive use), Cursor extensions, system fixes, the four `scripts/` init scripts (init-root.sh, init-user.sh, shell-init.sh, shell-env.sh), and `local-bin/`
- `Containerfile.base` also enables `sshd` and redirects its `HostKey` paths to `/var/lib/box-ssh` so host keys survive container recreates — see the "SSH host keys per box" bullet under box.toml Conventions for the mount each init box must pair with it
- **All sshd config lives in `sshd_config.d` drop-ins in the image, never in `/etc/ssh/sshd_config`.** That file is in the container's writable layer, so an edit made inside a box is silently reverted by the next recreate (`replace = true` everywhere) — the box then quietly returns to the packaged defaults, which is how a hardened setting can disappear without anyone noticing. `10-box-auth.conf` sets `PasswordAuthentication no` + `KbdInteractiveAuthentication no`; `10-box-host-keys.conf` sets the `HostKey` paths. Both directives are required for key-only auth: `UsePAM yes` lets keyboard-interactive reach `pam_unix` and accept the same password even when `PasswordAuthentication` is `no`. Password auth is a genuine exposure in `priv`/`work` specifically — their `init_hooks` copy the host's shadow hash into the container, so the box would accept the host login password over a tailnet-reachable sshd. The `10-` prefix is load-bearing: `/etc/ssh/sshd_config` `Include`s the drop-in dir on line 2 and sshd keeps the **first** value obtained for a keyword, so `10-` wins over both the main file and Arch's `99-archlinux.conf`. Do not "fix" a locked-out box by re-enabling passwords — `box enter` uses `podman exec` and bypasses sshd entirely, so lockout is not possible; add a key to `~/distrobox/<box>/home/.ssh/authorized_keys` instead
- **Per-box tmux server**: `Containerfile.base` hooks `shell-env.sh` into `/etc/zsh/zshenv` and `/etc/profile.d/box-env.sh`, and it exports `TMUX_TMPDIR="$HOME/.local/state/tmux"`. distrobox bind-mounts the host's `/tmp` into every box, and tmux derives its socket from `$TMUX_TMPDIR` (default `/tmp`) as `$TMUX_TMPDIR/tmux-$UID/default` — so with it unset the host and *all* boxes drive one shared tmux server. That matters because tmux forks panes from the **server's** environment, not the client's: a pane opened from workbox while the server was started from privbox gets privbox's `HOME` and `PATH`, so tools silently run against the wrong home. Since each box mounts a different host dir as `$HOME`, keying off `$HOME` gives one server per box. It is **not** keyed off `$XDG_RUNTIME_DIR` (also isolating) because that is a container-private tmpfs — the box's socket would be invisible from the host and `ssh <host>` + `tmux attach` would break, whereas box homes are visible from the host at the same path. Within `$HOME` it uses `.local/state/` and not `~/.tmux`, which is already tmux's own namespace (`~/.tmux.conf`, and `~/.tmux/plugins/` for TPM), and it deliberately ignores `$XDG_STATE_HOME` — that variable is inherited by `distrobox enter`, so honouring it would let one environment aim another's tmux at a shared dir. Deriving strictly from `$HOME` is what makes the scheme hold. For the same reason the assignment is unconditional, not "only if unset". Per-command overrides still work: `TMUX_TMPDIR=/tmp tmux attach`. Coverage is complete for zsh and login-only for bash/sh; `BASH_ENV` is deliberately not used (ssh and sudo strip it) — see the header of `scripts/shell-env.sh`. The host needs its own half of this in `~/.bashrc` — it is outside this repo, so it is not shipped here
- **Smartcards/YubiKeys use the host's `pcscd`, never one in the box.** `Containerfile.base` installs the client side (`yubikey-manager`, `libfido2`, `opensc`, `yubico-piv-tool`, `pcsc-tools`; `pcsclite` and `ccid` come in as deps) and then **masks `pcscd.service` and `pcscd.socket`**. Do not "fix" that by enabling them, and do not follow the [Arch wiki YubiKey page](https://wiki.archlinux.org/title/YubiKey) on this point — its `enable pcscd.service` step assumes a normal host. Two reasons: distrobox's entrypoint forwards every host `/run` socket into the box, so `/run/pcscd/pcscd.comm` is already a symlink to the host daemon (the same shadowing mechanism as the tailscale socket); and pcscd needs exclusive USB access to the reader, which no box has — podman gives each container a minimal `/dev` with no `/dev/bus/usb` and no `/dev/hidraw*`, which is also why the tailnet boxes must pass `--device /dev/net/tun` explicitly. An in-box pcscd would find no reader *and* clobber the working socket. **What this buys and costs:** the CCID applets are the ones that can work in a box (`ykman info`, `ykman piv|oath|openpgp`, PIV-backed SSH via PKCS#11, `gpg --card-status`), while the HID transports cannot — `fido2-token`, `ssh-keygen -t ed25519-sk`, `ykman otp|fido`, and WebAuthn in the exported Chrome all open `/dev/hidraw*` directly and must be run on the host. Making those work in a box is a `box.toml` device-passthrough change, not an unmask
- **`WARNING: PC/SC not available` in `priv`/`work` is polkit, not a broken daemon — and the fix is host-side, so it does not belong in this repo.** pcscd grants `org.debian.pcsc-lite.access_pcsc`/`access_card` on `allow_active` only. Rootless boxes (`dev`) are parented under `user@1000.service`, so host logind resolves them to the user's active session and allows them; rootful boxes (`priv`, `work`) are parented under `machine.slice` with no session at all and are denied, which pcscd returns as `SCARD_W_SECURITY_VIOLATION` (0x8010006A) — easy to misdiagnose as a dead daemon. Confirm without changing anything using polkit's own decision procedure on the host: `pkcheck --action-id org.debian.pcsc-lite.access_pcsc --process <host-pid-of-a-uid-1000-process-in-the-box>`. The lift is a `/etc/polkit-1/rules.d/` rule on the host, documented in `README.md` as an opt-in host step and **intentionally not shipped here** — it is host- and user-specific, and it relaxes a security default that forks should opt into consciously. Do not try to "tighten" it with `subject.local`/`subject.active` (both derive from the missing session, so the rule would never match) or with `polkit.Result.AUTH_*` (session-less processes have no authentication agent, so it fails closed). Two traps when investigating: the Bash sandbox blocks AF_UNIX socket creation, so PC/SC probes there report a misleading `SCARD_E_NO_SERVICE` and `host-spawn` silently returns nothing — use `dangerouslyDisableSandbox`; and the boxes have their own PID namespace, so a missing `/proc/<pid>` for the pid in `pcscd.pid` proves nothing about the host daemon
- `Containerfile.base` installs `host-spawn` to `/usr/bin/host-spawn` from a version-pinned, sha256-checked upstream release (it is in neither the official repos nor the AUR). distrobox's `/etc/profile.d/distrobox_profile.sh` (every login shell) and `distrobox-host-exec` both require it, but distrobox bind-mounts only its own shell scripts and no binary — the host has none either. Its fallback is a silent best-effort download during `distrobox-init` (`distrobox-host-exec -Y test ... || :`) into the writable layer that every `replace = true` recreate discards. That download lands in `dev` but not in `priv`/`work`; the untested suspect is egress at init time inside their own netns (`unshare_netns = true`). **Maintenance contract:** keep the pinned version at or above the `host_spawn_version` that the host's `distrobox-host-exec` requires, otherwise `distrobox-host-exec` starts prompting to download a newer one again. The binary dispatches on its own `argv[0]` — never rename it or symlink another command name to it unless you intend that command to run on the host
- **AUR builds are locked to vendored PKGBUILDs** — the build runs `makepkg` against `aur/<pkgbase>/`, never `yay -S`/`git clone` from the AUR. This is a supply-chain control (the AUR is regularly hit by account-takeover attacks); a malicious upstream PKGBUILD change cannot reach an image until reviewed in a PR. `makepkg` still downloads each upstream artifact, but only from the official URL in the vetted PKGBUILD, gated by its committed checksums. See `aur/README.md`.
- Box-specific Containerfiles (`priv/Containerfile`, `work/Containerfile`, `dev/Containerfile`) declare `ARG BASE_IMAGE=ghcr.io/gablank/box-base:latest` followed by `FROM ${BASE_IMAGE}`. CI overrides `BASE_IMAGE` to point to the fork owner's registry.
- Build context is always the repo root
- Both base and box Containerfiles accept `BUILD_DATE` and `BUILD_SHA` build args, written to `/etc/box-build-info`
- Always clean caches at the end of a Containerfile (`pacman -Scc --noconfirm`, `rm -rf /var/cache/pacman/pkg/*`)

### Adding a package

- Official, needed by all boxes: add to `Containerfile.base` `pacman -S --noconfirm --needed <pkg>`
- AUR, needed by all boxes: **never** add a `yay -S` line. Vendor and vet the PKGBUILD first (`box vendor-aur <pkgbase>`, review the diff, commit `aur/`), then add a `makepkg` build step to the AUR section of `Containerfile.base`. Split pkgbases follow the `google-cloud-cli` pattern (build once, `pacman -U` only the wanted outputs). See `aur/README.md`.
- Needed by one box: add to that box's Containerfile (official deps only; AUR follows the vendored flow above)

### Adding a Cursor extension

Add it to the extension install loop in `Containerfile.base`.

## bin/box CLI

- Pure bash, uses `distrobox` and `curl`; no `gh` CLI required
- Box argument is always the directory name (`priv`, `work`), not the container name
- Auto-discovers boxes by scanning for `*/box.toml`
- `OWNER` is auto-detected from the git remote URL (`github.com:<owner>/...`); override with `BOX_OWNER` env var
- `box init [owner]` updates the `image = ` line in all `box.toml` files (then recompiles to `distrobox.ini`) to use the specified (or auto-detected) owner; called automatically by `setup.sh`
- `box set-image <box> [tag]` updates the `image = ` line in `box.toml` and recompiles (default: `latest`); does not rebuild
- `box assemble <box>` recompiles `box.toml` → `distrobox.ini` and runs `distrobox assemble create`; does not touch the image tag
- `box assemble-all` assembles all boxes
- `box pull <box> [tag]` pulls the image via `podman pull` without touching the container or ini; uses the tag currently in the ini if none specified
- `box upgrade <box>` sets the tag to `latest`, pulls, and reassembles — the one-command upgrade path
- `box build [--no-cache] <box>` builds base + box images locally; layer cache is used unless `--no-cache` is given
- `box images <box>` lists available tags with a human-readable age column; marks the tag the container is built from with `← current` (green) and the tag the next `assemble` will use with `← next` (yellow)
- `box vendor-aur <pkgbase>... | --all` re-clones AUR PKGBUILDs into `aur/`, prints a diff against the committed copy to vet, and updates `aur/manifest.tsv`; wraps `scripts/vendor-aur.sh`. Use it to bump a stale vendored `-bin`/`-git` package (review the diff, then commit `aur/`). **Vetting that diff is the whole point of vendoring** — follow the step-by-step audit procedure in `aur/README.md` ("Auditing a `vendor-aur` bump") rather than eyeballing it: a routine bump is nothing but version/checksum/manifest lines, and everything else needs justification
- Common workflows:
  - Upgrade to latest: `box upgrade priv`
  - Rollback: `box set-image priv <tag> && box pull priv <tag> && box assemble priv`
  - Recreate without re-pulling: `box assemble priv`
- To add a command: add `cmd_<name>()` function (use `_` for hyphens in function name), add the case in the dispatch block, update `usage()`, **and add the command name to `_BOX_COMMANDS`** (see Completions sync contract below)
- `box completions <bash|zsh|install>` — prints or installs shell completions; `install` appends `eval "$(box completions <shell>)"` to the user's rc file so completions always reflect the current `bin/box`

## Completions Sync Contract

**Single source of truth for command names:** `_BOX_COMMANDS` array at the top of `bin/box`.

When adding a new command:
1. Add `cmd_<name>()` and the case entry (as above)
2. **Add the name to `_BOX_COMMANDS`** — the CI `lint` job will fail if a case dispatch command is missing from `_BOX_COMMANDS`
3. If the command takes `<box>` as its first argument, also add it to `_BOX_COMMANDS_WITH_BOX`
4. If the command needs a description in zsh tab-completion, add a line to the `_box_commands()` helper inside `_completions_zsh()`

The completion heredocs **interpolate** the command lists from the arrays at runtime via placeholder substitution (`@@CMDS@@`, `@@BOX_CMDS@@`): the bash top-level list comes from `_BOX_COMMANDS`, and the box-taking subset in both shells comes from `_BOX_COMMANDS_WITH_BOX`. You do **not** hand-edit those lists — keeping the arrays correct (steps 2–3) is enough. The only manually maintained completion text is the descriptive `_box_commands()` list in zsh (step 4).

**Box names** are always discovered dynamically via `box --list-boxes` at completion time — no manual sync needed when adding a new box.

**CI enforcement:** The `lint` job in `.github/workflows/build.yml` runs on every push and verifies:
- Every `*/box.toml` compiles cleanly with `scripts/compile-box-toml.py`
- `box completions bash` and `box completions zsh` both exit 0 and contain every entry in `_BOX_COMMANDS`
- Every command extracted from the `case` dispatch block exists in `_BOX_COMMANDS`
- Every `box <cmd>` invocation documented in `README.md`, `AGENTS.md`, the skills, and `setup.sh` exists in `_BOX_COMMANDS` (catches stale command names in docs)
- `shellcheck --severity=error` passes on `bin/box`, `scripts/*.sh`, and `setup.sh`

## Local checks

There is no test suite; the CI `lint` job is the only gate. Mirror it locally before pushing. The `dev` box ships `shellcheck` (added in `dev/Containerfile`) so the static-analysis step below runs out of the box:

```bash
# Every box.toml must compile cleanly.
for d in */; do
  if [ -f "$d/box.toml" ]; then python3 scripts/compile-box-toml.py "$d" || exit 1; fi
done

# Every _BOX_COMMANDS entry must appear in both completion outputs.
# Run under bash — `mapfile` is bash-only.
bash -c '
  mapfile -t declared < <(grep -oP "(?<=_BOX_COMMANDS=\()[^)]*" bin/box | tr " " "\n" | tr -d "()" | grep -v "^$")
  for sh in bash zsh; do
    out="$(bin/box completions "$sh")"
    for cmd in "${declared[@]}"; do
      grep -q "$cmd" <<<"$out" || echo "MISSING from $sh: $cmd"
    done
  done
'

# Static analysis (CI runs this at --severity=error)
shellcheck --severity=error --shell=bash bin/box scripts/*.sh setup.sh
```

## Shell Script Style

- Shebang: `#!/usr/bin/env bash`
- Always `set -euo pipefail`
- Quote all variable expansions: `"$var"`
- Use `printf` over `echo` for formatted output
- Use `local` for function-scoped variables
- ANSI colors via `$'\033[...'` (dollar-quote syntax)
- No comments explaining obvious code

## box.toml Conventions

`box.toml` is the source of truth; `distrobox.ini` is generated by `scripts/compile-box-toml.py` and gitignored. **Never edit the ini directly.**

- `home` and `[[mount-dir]]` host paths use `${HOME}` / `${XDG_RUNTIME_DIR}` — expanded by distrobox on the host, never hardcode paths
- `init_hooks` use `${container_user_name}` (a distrobox-init shell variable guaranteed in scope at eval time) — **not** `${USER}`, which is unbound when init_hooks run inside the container
- `[[mount-dir]]` entries become `volume=` lines (auto-created on host); `[[mount-file]]` entries become `--volume` flags in `additional_flags` (must already exist)
- All boxes use `--security-opt seccomp=unconfined` (required for bubblewrap/bwrap inside the container)
- **Tailscale per-box**: each box has its own tailscale node (different tailnet per box) via `unshare_netns=true`. The box's user namespace owns the netns, making `CAP_NET_ADMIN` valid for `TUNSETIFF`. Setup:
  - `unshare_netns=true`
  - `[[mount-dir]]` for `${HOME}/distrobox/<box>/tailscale:/var/lib/tailscale` — persists auth state across recreates
  - `--device /dev/net/tun --cap-add NET_ADMIN --cap-add NET_RAW` in `additional_flags`
  - **No init_hooks tweaks needed.** The base image ships a systemd drop-in that runs `tailscaled` with `--socket=/var/run/tailscale/box.sock` and a `/usr/bin/tailscale` wrapper that injects the same flag. This sidesteps the issue where distrobox-init symlinks the host's tailscale socket over the default path inside the container. See `Containerfile.base` for the wrapper definition; `IgnorePkg` keeps in-container `pacman -Syu` from overwriting it.
  - After first `box assemble <box>`, run `tailscale up` inside the box to authenticate
- **SSH host keys per box**: any box with `init = true` runs `sshd`, and stock `sshd` keeps its host keys in `/etc/ssh` — the container's writable layer, wiped by every recreate. Because `replace = true` means `box upgrade`/`assemble`/`rescue` all recreate, and because tailscale state *is* persisted (so the box keeps its name and IP), the box would come back with a new SSH identity at the same address and every client would report `REMOTE HOST IDENTIFICATION HAS CHANGED`. The base image points `HostKey` at `/var/lib/box-ssh` instead, so **every init box needs**:
  ```toml
  [[mount-dir]]
  host = "${HOME}/distrobox/<box>/ssh-hostkeys"
  container = "/var/lib/box-ssh"
  options = "rw,z"
  ```
  Nothing else — `/usr/local/sbin/box-sshd-keygen` runs from an `sshd.service` `ExecStartPre` drop-in and creates only missing keys, so the identity is stable from the first start onward. Keys are never baked into the image (public repo). Delete the host directory to deliberately rotate a box's SSH identity.
- **Docker-compose + work tailnet**: to make compose services reachable from the work box *and* on the work tailnet, add `network_mode: "container:workbox"` to each service in the compose file. Services then share workbox's network namespace; use `localhost:PORT` to reach them from the box.
- See `.agents/skills/box-toml-conventions/SKILL.md` for the full template and field reference

## Adding or Removing a Box

Follow the complete checklist in `.agents/skills/adding-a-box/SKILL.md`. It covers creating the box directory, updating CI, and updating all documentation files.

**CI path filter maintenance:** The `changes` job in `.github/workflows/build.yml` uses `dorny/paths-filter` to detect changes and builds a dynamic `box_matrix` JSON array consumed by `build-boxes` via `fromJson`. It must be kept in sync with the repo layout:
- New box → add a filter entry for `<name>/**` and wire it into the `boxes` array in the `Compute build flags` step
- New shared directory (e.g. a new top-level dir copied into all images) → add it to the `base:` filter
- Renamed or moved directory → update the matching filter entry

Whenever you add something to CI that is gated by a path filter, document what must be updated here and in the relevant skill.
