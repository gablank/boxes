#!/usr/bin/env bash
# Sourced from ~/.zshrc — all box runtime env and services live here.
# Changes to this file take effect on next shell open (no box rebuild needed).

# --- Environment ---
export DOCKER_HOST="unix:///podman.sock"

# --- Tailscale ---
# Restart box tailscaled if the socket is missing (e.g. after host reboot).
# The init_hooks rm the host symlink distrobox creates, but on reboot
# the socket disappears entirely so tailscaled needs a fresh start.
if [[ -d /var/lib/tailscale ]] && ! [[ -S /var/run/tailscale/tailscaled.sock ]]; then
    sudo rm -f /var/run/tailscale/tailscaled.sock
    sudo tailscaled --statedir=/var/lib/tailscale &>/tmp/tailscaled.log &
fi
