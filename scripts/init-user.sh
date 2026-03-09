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

if [[ -d /var/lib/tailscale ]]; then
    ensure_env "$HOME/.zshenv" TS_SOCKET "/var/run/tailscale-box/tailscaled.sock"
    if ! grep -qF 'tailscale-box' ~/.zshrc 2>/dev/null; then
        printf '\n# Auto-restart box tailscaled on shell open if socket is gone (e.g. after host reboot)\nif [[ -d /var/lib/tailscale ]] && ! [[ -S /var/run/tailscale-box/tailscaled.sock ]]; then\n    sudo mkdir -p /var/run/tailscale-box\n    sudo tailscaled --statedir=/var/lib/tailscale --socket=/var/run/tailscale-box/tailscaled.sock &>/tmp/tailscaled.log &\nfi\n' >> ~/.zshrc
    fi
fi

printf '[box-init] user init done\n'
