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

# --- Host D-Bus for desktop-launched apps ---
# Desktop entries bypass shell init, so set the host bus in /etc/environment
# where PAM reads it for all sessions (including machinectl shell).
readonly host_bus="unix:path=/run/host/run/user/$(id -u)/bus"
if ! grep -qF 'DBUS_SESSION_BUS_ADDRESS' /etc/environment 2>/dev/null; then
    printf 'DBUS_SESSION_BUS_ADDRESS=%s\n' "$host_bus" | sudo tee -a /etc/environment >/dev/null
fi

printf '[box-init] user init done\n'
