#!/usr/bin/env bash
# Execution context: runs as the CONTAINER USER via su from init_hooks,
# AFTER init-root.sh. No TTY is available — sudo and interactive commands
# will fail. Root-level setup belongs in init-root.sh.
set -euo pipefail

printf '[box-init] user init start\n'

# --- One-time setup ---
mkdir -p ~/.ssh
chmod 700 ~/.ssh

if [[ ! -f ~/.zshrc ]] && [[ -f /etc/skel/.zshrc ]]; then
    cp /etc/skel/.zshrc ~/.zshrc
fi

# --- Source shell-init.sh from .zshrc ---
readonly source_line='source /usr/local/share/box-init/shell-init.sh'
if ! grep -qF "$source_line" ~/.zshrc 2>/dev/null; then
    printf '\n%s\n' "$source_line" >> ~/.zshrc
fi

printf '[box-init] user init done\n'
