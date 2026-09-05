#!/usr/bin/env bash
# Execution context: sourced from ~/.zshrc as the CONTAINER USER in an
# interactive shell. TTY is available. Unlike init-root.sh and init-user.sh,
# this runs on every shell open, not just first container start.
# All box runtime env and services live here.
# Changes to this file take effect on next shell open (no box rebuild needed).
#
# Interactive-only. Anything a NON-interactive shell (`zsh -c ...`, a script, a
# desktop launcher) must also see belongs in shell-env.sh, which the base image
# wires into /etc/zsh/zshenv and /etc/profile.d instead.

# --- SSH/sudo askpass (drop leaked host askpass) ---
# The host (KDE) exports SSH_ASKPASS/SUDO_ASKPASS pointing at a GUI helper
# (/usr/bin/ksshaskpass) plus DISPLAY into the box. That helper is host-only and
# does not exist here, so when ssh needs to prompt (e.g. confirming an unknown
# host key) it tries to exec the missing askpass, fails, and aborts with
# "Host key verification failed"; sudo -A hits the same wall.
#
# Rather than match a specific binary name, drop any askpass var whose target is
# not an executable in this box — this stays correct no matter which host helper
# leaks in. Falling back to the terminal prompt is what we want in a CLI box.
[[ -n "${SSH_ASKPASS:-}"  && ! -x "${SSH_ASKPASS}"  ]] && unset SSH_ASKPASS
[[ -n "${SUDO_ASKPASS:-}" && ! -x "${SUDO_ASKPASS}" ]] && unset SUDO_ASKPASS
# SSH_ASKPASS_REQUIRE=force makes ssh use askpass even when a tty is present;
# pointless once SSH_ASKPASS is gone, so clear it too.
[[ -z "${SSH_ASKPASS:-}" ]] && unset SSH_ASKPASS_REQUIRE

# --- Container runtime (docker CLI → podman) ---
# Two modes:
#   1. Host podman shared in: box.toml mounts the host's socket at /podman.sock
#      (priv). Containers run on the host, in the host's netns.
#   2. Box-local rootless podman: no /podman.sock mount, podman daemon installed
#      in the image (workbox). Containers run inside the box's own netns, so
#      `localhost:<port>` from a shell in the box reaches them.
if [[ -S /podman.sock ]]; then
    export DOCKER_HOST="unix:///podman.sock"
elif command -v podman >/dev/null 2>&1; then
    systemctl --user enable --now podman.socket >/dev/null 2>&1 || true
    _box_podman_sock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
    [[ -S "$_box_podman_sock" ]] && export DOCKER_HOST="unix://$_box_podman_sock"
    unset _box_podman_sock
fi

# Point podman at docker's config file so `credHelpers` from
# `gcloud auth configure-docker` are honored. Without this, podman's default
# lookup ($XDG_RUNTIME_DIR/containers/auth.json first) shadows ~/.docker/config.json
# the moment anything writes a login token there.
export REGISTRY_AUTH_FILE="$HOME/.docker/config.json"

[[ "$(pwd)" == /run/host/* ]] && cd ~

# --- Host session D-Bus and audio: NOT here ---
# DBUS_SESSION_BUS_ADDRESS and PULSE_SERVER used to be set in this file. They
# now live in shell-env.sh, because distrobox's /etc/profile.d/
# distrobox_profile.sh needs the bus address *before* ~/.zshrc is reached: it
# calls host-spawn over the session bus and, with the wrong address, fails with
# "dial unix /run/user/1000/bus: ... no such file or directory". Do not move
# them back — see the comment in shell-env.sh.

# --- Rust (rustup) ---
# Rustup installs toolchain proxy shims (cargo, rustc, rustfmt, ...) to
# ~/.cargo/bin. The Arch rustup package does not modify PATH automatically.
[[ -d "$HOME/.cargo/bin" ]] && export PATH="$HOME/.cargo/bin:$PATH"

# --- Per-box prompt badge ---
# Make it obvious which box a shell belongs to. CONTAINER_ID is set by distrobox
# to the container name; the hostname is shared with the host so it can't be used.
# Each box gets a distinct color. This runs after oh-my-zsh has set PROMPT (the
# source line is appended below the theme in ~/.zshrc), so we prepend to it.
if [[ -n "${ZSH_VERSION:-}" ]] && [[ -n "${CONTAINER_ID:-}" ]]; then
    case "$CONTAINER_ID" in
        workbox) _box_color="yellow" ;;
        privbox) _box_color="red" ;;
        devbox)  _box_color="blue" ;;
        *)       _box_color="white" ;;
    esac
    PROMPT="%F{$_box_color}[${CONTAINER_ID%box}]%f $PROMPT"
    unset _box_color
fi
