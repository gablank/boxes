#!/usr/bin/env bash
# Sourced from ~/.zshrc — all box runtime env and services live here.
# Changes to this file take effect on next shell open (no box rebuild needed).

# --- Environment ---
export DOCKER_HOST="unix:///podman.sock"

# --- Tailscale ---
# Distrobox-enter recreates a host symlink at the default socket path on
# every entry. Remove it so the tailscale CLI talks to the box daemon.
# If tailscaled isn't running (e.g. after host reboot), start it.
if [[ -d /var/lib/tailscale ]]; then
    if [[ -L /var/run/tailscale/tailscaled.sock ]]; then
        sudo rm -f /var/run/tailscale/tailscaled.sock
    fi
    if ! pgrep -x tailscaled &>/dev/null; then
        sudo tailscaled --statedir=/var/lib/tailscale &>/tmp/tailscaled.log &
    fi
fi
