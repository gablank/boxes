#!/usr/bin/env bash
# Execution context: runs as ROOT inside the container, called from init_hooks
# in box.toml BEFORE su to the container user. No TTY is available.
# Do NOT add user-level setup here; use init-user.sh for that.
set -euo pipefail

readonly user="${1:?Usage: init-root.sh <username>}"

printf '[box-init] root init start\n'

# Set timezone from box.toml (compiled into box-assembled.ini as box-meta comment)
tz="$(grep -oP '^# box-meta:timezone=\K.+' /etc/box-assembled.ini 2>/dev/null || true)"
if [[ -n "$tz" ]]; then
    if [[ -f "/usr/share/zoneinfo/$tz" ]]; then
        ln -sf "/usr/share/zoneinfo/$tz" /etc/localtime
        printf '[box-init] timezone set to %s\n' "$tz"
    else
        printf '[box-init] ERROR: timezone %s not found in /usr/share/zoneinfo\n' "$tz" >&2
    fi
fi

# Set login shell — chsh requires root or user password, so must run here
chsh -s /usr/bin/zsh "$user" >/dev/null 2>&1 || true

# Set env vars for desktop-launched apps that bypass shell init.
# shell-init.sh handles interactive shells; /etc/environment covers
# apps launched via distrobox-export desktop entries (PAM reads this).
readonly host_runtime="/run/host/run/user/$(id -u "$user")"
if ! grep -qF 'DBUS_SESSION_BUS_ADDRESS' /etc/environment 2>/dev/null; then
    printf 'DBUS_SESSION_BUS_ADDRESS=unix:path=%s/bus\n' "$host_runtime" >> /etc/environment
fi
if ! grep -qF 'PULSE_SERVER' /etc/environment 2>/dev/null; then
    printf 'PULSE_SERVER=unix:%s/pulse/native\n' "$host_runtime" >> /etc/environment
fi

printf '[box-init] root init done\n'
