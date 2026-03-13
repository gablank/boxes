#!/usr/bin/env bash
set -euo pipefail

printf '[box-init] user init start\n'

# --- One-time setup ---
mkdir -p ~/.ssh
chmod 700 ~/.ssh

if [[ ! -f ~/.zshrc ]] && [[ -f /etc/skel/.zshrc ]]; then
    cp /etc/skel/.zshrc ~/.zshrc
fi

chsh -s /usr/bin/zsh "$USER" >/dev/null 2>&1 || true

# --- Source shell-init.sh from .zshrc ---
readonly source_line='source /usr/local/share/box-init/shell-init.sh'
if ! grep -qF "$source_line" ~/.zshrc 2>/dev/null; then
    printf '\n%s\n' "$source_line" >> ~/.zshrc
fi

# --- Host sockets for desktop-launched apps ---
# Desktop entries bypass shell init, so set these in /etc/environment
# where PAM reads them for all sessions (including machinectl shell).
readonly host_runtime="/run/host/run/user/$(id -u)"
if ! grep -qF 'DBUS_SESSION_BUS_ADDRESS' /etc/environment 2>/dev/null; then
    printf 'DBUS_SESSION_BUS_ADDRESS=unix:path=%s/bus\n' "$host_runtime" | sudo tee -a /etc/environment >/dev/null
fi
if ! grep -qF 'PULSE_SERVER' /etc/environment 2>/dev/null; then
    printf 'PULSE_SERVER=unix:%s/pulse/native\n' "$host_runtime" | sudo tee -a /etc/environment >/dev/null
fi

printf '[box-init] user init done\n'
