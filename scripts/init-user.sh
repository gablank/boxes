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

# --- Install default Rust toolchain via rustup (idempotent) ---
if command -v rustup >/dev/null 2>&1 && ! rustup show active-toolchain >/dev/null 2>&1; then
    rustup default stable
fi

# --- Source shell-init.sh from .zshrc ---
readonly source_line='source /usr/local/share/box-init/shell-init.sh'
if ! grep -qF "$source_line" ~/.zshrc 2>/dev/null; then
    printf '\n%s\n' "$source_line" >> ~/.zshrc
fi

# --- Agent brief for Codex (Claude Code gets it from /etc/claude-code/CLAUDE.md) ---
# Codex has no machine-wide instruction file: it reads $CODEX_HOME/AGENTS.md
# (default ~/.codex/AGENTS.md) at the start of every session, whatever the cwd.
# A symlink keeps it current — the target is refreshed by each image rebuild,
# so the brief tracks the repo without re-copying it into every home.
# Only ever created when nothing is there: a real file at that path is the
# user's own, and clobbering it would silently drop their instructions. To take
# it over, replace the symlink with a real file (and paste in whatever of
# /usr/local/share/box-init/box-brief.md still applies).
readonly codex_brief=/usr/local/share/box-init/box-brief.md
if [[ -f "$codex_brief" ]] && [[ ! -e ~/.codex/AGENTS.md ]]; then
    mkdir -p ~/.codex
    ln -sfn "$codex_brief" ~/.codex/AGENTS.md
fi

printf '[box-init] user init done\n'
