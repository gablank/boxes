#!/usr/bin/env bash
# Execution context: sourced from ~/.zshrc as the CONTAINER USER in an
# interactive shell. TTY is available. Unlike init-root.sh and init-user.sh,
# this runs on every shell open, not just first container start.
# All box runtime env and services live here.
# Changes to this file take effect on next shell open (no box rebuild needed).

# --- Environment ---
export DOCKER_HOST="unix:///podman.sock"

[[ "$(pwd)" == "/run/host/home/awenhaug" ]] && cd ~

# --- D-Bus ---
# Use the host's session bus so xdg-desktop-portal works for screen sharing.
# Distrobox exposes host sockets under /run/host; the container's own systemd
# dbus sits at the default path, so we point at the host's socket explicitly.
if [[ -S "/run/host${XDG_RUNTIME_DIR}/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/host${XDG_RUNTIME_DIR}/bus"
fi

# --- Audio ---
# Point PulseAudio/PipeWire clients at the host's sockets. The container's own
# sockets at /run/user/*/pulse and /run/user/*/pipewire-0 are dead (created by
# distrobox-enter but not connected to anything in init containers).
if [[ -S "/run/host${XDG_RUNTIME_DIR}/pulse/native" ]]; then
    export PULSE_SERVER="unix:/run/host${XDG_RUNTIME_DIR}/pulse/native"
fi

# --- Tailscale ---
# tailscaled uses a custom socket path (/var/run/tailscale/box.sock) to avoid
# distrobox-enter overwriting the default path with a host symlink on every entry.
# Point the CLI at the custom socket.
if [[ -d /var/lib/tailscale ]]; then
    alias tailscale='tailscale --socket=/var/run/tailscale/box.sock'
fi
