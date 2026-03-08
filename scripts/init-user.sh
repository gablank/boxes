#!/usr/bin/env bash
set -euo pipefail

printf '[box-init] user init start\n'

ensure_env() {
    local file="$1" key="$2" value="$3"
    mkdir -p "$(dirname "$file")"
    touch "$file"
    if grep -qE "^export ${key}=" "$file"; then
        sed -i "s|^export ${key}=.*$|export ${key}=${value}|" "$file"
    else
        printf 'export %s=%s\n' "$key" "$value" >> "$file"
    fi
}

mkdir -p ~/.ssh
chmod 700 ~/.ssh

if [[ ! -f ~/.zshrc ]] && [[ -f /etc/skel/.zshrc ]]; then
    cp /etc/skel/.zshrc ~/.zshrc
fi

ensure_env "$HOME/.zshenv"  DOCKER_HOST "unix:///podman.sock"
ensure_env "$HOME/.profile" DOCKER_HOST "unix:///podman.sock"

chsh -s /usr/bin/zsh "$USER" >/dev/null 2>&1 || true

if [[ -d /var/lib/tailscale ]] && ! grep -qF 'tailscaled' ~/.zshrc 2>/dev/null; then
    printf '\n# Auto-start tailscaled on shell open (only if state dir is mounted)\nif [[ -d /var/lib/tailscale ]] && ! pgrep -x tailscaled &>/dev/null; then\n    sudo tailscaled --statedir=/var/lib/tailscale &>/tmp/tailscaled.log &\nfi\n' >> ~/.zshrc
fi

printf '[box-init] user init done\n'
