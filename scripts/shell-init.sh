#!/usr/bin/env bash
# Sourced from ~/.zshrc — all box runtime env and services live here.
# Changes to this file take effect on next shell open (no box rebuild needed).

# --- Environment ---
export DOCKER_HOST="unix:///podman.sock"

# --- D-Bus ---
# Use the host's session bus so xdg-desktop-portal works for screen sharing.
# Distrobox exposes host sockets under /run/host; the container's own systemd
# dbus sits at the default path, so we point at the host's socket explicitly.
if [[ -S "/run/host${XDG_RUNTIME_DIR}/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/host${XDG_RUNTIME_DIR}/bus"
fi

# --- Tailscale ---
# tailscaled uses a custom socket path (/var/run/tailscale/box.sock) to avoid
# distrobox-enter overwriting the default path with a host symlink on every entry.
# Point the CLI at the custom socket.
if [[ -d /var/lib/tailscale ]]; then
    alias tailscale='tailscale --socket=/var/run/tailscale/box.sock'
fi
