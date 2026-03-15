#!/usr/bin/env bash
#
# LinuxShot Uninstaller
#
set -euo pipefail

GREEN='\033[32m'
CYAN='\033[36m'
BOLD='\033[1m'
RESET='\033[0m'

info() { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()   { echo -e "${GREEN}[OK]${RESET}    $*"; }

echo -e "${BOLD}Uninstalling LinuxShot...${RESET}"
echo ""

# Remove pip package
info "Removing LinuxShot Python package..."
pip uninstall -y linuxshot 2>/dev/null || \
    pip3 uninstall -y linuxshot 2>/dev/null || \
    true
ok "Package removed."

# Remove desktop file
DESKTOP_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/linuxshot.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    ok "Desktop file removed."
fi

# Ask about config/data
echo ""
read -p "Remove config and history data? (~/.config/linuxshot, ~/.local/share/linuxshot) [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/linuxshot"
    rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/linuxshot"
    ok "Config and data removed."
else
    info "Config and data preserved."
fi

echo ""
echo -e "${GREEN}${BOLD}LinuxShot has been uninstalled.${RESET}"
