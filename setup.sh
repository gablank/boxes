#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
BOX_BIN="$REPO_ROOT/bin/box"
REPO_BIN="$REPO_ROOT/bin"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

check_cmd() {
    local cmd="$1" install_hint="${2:-}"
    if ! command -v "$cmd" &>/dev/null; then
        printf "${RED}Error: '%s' is required but not found.${RESET}\n" "$cmd" >&2
        [[ -n "$install_hint" ]] && printf "  %s\n" "$install_hint" >&2
        exit 1
    fi
}

printf "${BOLD}Box Setup${RESET}\n\n"

printf "${CYAN}Checking prerequisites...${RESET}\n"
check_cmd git   "Install git via your system package manager."
check_cmd podman "Install podman: https://podman.io/docs/installation"
check_cmd distrobox "Install distrobox: https://distrobox.it/#installation"
printf "${GREEN}All prerequisites found.${RESET}\n\n"

# Add repo bin/ to PATH via shell rc files
PATH_LINE="export PATH=\"$REPO_BIN:\$PATH\""
added=false
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [[ -f "$rc" ]] && ! grep -qF "$REPO_BIN" "$rc"; then
        printf '\n# Added by boxes setup.sh\n%s\n' "$PATH_LINE" >> "$rc"
        printf "${GREEN}Added bin/ to PATH in %s${RESET}\n" "$rc"
        added=true
    fi
done

if ! echo ":${PATH}:" | grep -q ":${REPO_BIN}:"; then
    export PATH="$REPO_BIN:$PATH"
    if [[ "$added" == false ]]; then
        printf "${YELLOW}Note: could not find ~/.bashrc or ~/.zshrc to update.${RESET}\n"
        printf "  Add this line manually: %s\n" "$PATH_LINE"
    fi
    printf "${YELLOW}PATH updated for this session. Restart your shell for it to persist.${RESET}\n"
fi
printf "\n"

# Set image registry owner in all distrobox.ini files based on git remote
printf "${CYAN}Configuring image registry...${RESET}\n"
"$BOX_BIN" init
printf "\n"

printf "${BOLD}Setup complete!${RESET}\n\n"
printf "Next steps:\n"
printf "  box stage priv    # pull privbox image\n"
printf "  box rebuild priv  # apply image and start privbox\n"
printf "  box enter priv    # enter privbox\n"
printf "\n"
printf "Run ${BOLD}box${RESET} with no arguments to see all available commands.\n"
