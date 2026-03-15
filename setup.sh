#!/usr/bin/env bash
#
# LinuxShot Setup Script
# Installs dependencies and LinuxShot on Arch/CachyOS, Debian/Ubuntu, and Fedora.
#
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
CYAN='\033[36m'
RESET='\033[0m'

info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()    { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║          LinuxShot Installer v1.0.0          ║"
echo "║   ShareX-inspired screenshot tool for Linux  ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Detect distro ──────────────────────────────────────────────────

detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            arch|cachyos|endeavouros|manjaro|garuda)
                echo "arch"
                ;;
            ubuntu|debian|pop|linuxmint|elementary|zorin)
                echo "debian"
                ;;
            fedora|centos|rhel|nobara)
                echo "fedora"
                ;;
            opensuse*|suse*)
                echo "suse"
                ;;
            void)
                echo "void"
                ;;
            *)
                echo "unknown"
                ;;
        esac
    else
        echo "unknown"
    fi
}

# ── Detect display server ──────────────────────────────────────────

detect_display() {
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        echo "wayland"
    elif [ "${XDG_SESSION_TYPE:-}" = "x11" ] || [ -n "${DISPLAY:-}" ]; then
        echo "x11"
    else
        echo "both"
    fi
}

DISTRO=$(detect_distro)
DISPLAY_SERVER=$(detect_display)
DESKTOP_ENV=$(echo "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')

info "Detected distro family: ${BOLD}${DISTRO}${RESET}"
info "Detected display server: ${BOLD}${DISPLAY_SERVER}${RESET}"
info "Detected desktop environment: ${BOLD}${XDG_CURRENT_DESKTOP:-unknown}${RESET}"
echo ""

# ── Install system dependencies ────────────────────────────────────

install_deps_arch() {
    info "Installing system packages via pacman..."

    local pkgs=(
        python python-pip python-gobject python-pillow python-requests
        gtk3 libnotify
    )

    # Display server specific
    if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        pkgs+=(grim slurp wl-clipboard)
        if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
            pkgs+=(spectacle)
        fi
    fi
    if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        pkgs+=(maim xdotool xclip)
    fi

    # AppIndicator for tray
    # Try libayatana-appindicator first, then libappindicator-gtk3
    pkgs+=(libayatana-appindicator)

    sudo pacman -S --needed --noconfirm "${pkgs[@]}" || {
        warn "Some packages may not be in official repos. Trying without optional ones..."
        sudo pacman -S --needed --noconfirm python python-pip python-gobject python-pillow python-requests gtk3 libnotify
        if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
            sudo pacman -S --needed --noconfirm grim slurp wl-clipboard
            if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
                sudo pacman -S --needed --noconfirm spectacle
            fi
        fi
        if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
            sudo pacman -S --needed --noconfirm maim xdotool xclip
        fi
    }
}

install_deps_debian() {
    info "Installing system packages via apt..."
    sudo apt update

    local pkgs=(
        python3 python3-pip python3-gi python3-pil python3-requests
        gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
        libnotify-bin
    )

    if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        pkgs+=(grim slurp wl-clipboard)
        if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
            pkgs+=(spectacle)
        fi
    fi
    if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        pkgs+=(maim xdotool xclip)
    fi

    sudo apt install -y "${pkgs[@]}" || {
        warn "Some packages may not be available. Installing core deps..."
        sudo apt install -y python3 python3-pip python3-gi python3-pil python3-requests gir1.2-gtk-3.0 libnotify-bin
    }
}

install_deps_fedora() {
    info "Installing system packages via dnf..."

    local pkgs=(
        python3 python3-pip python3-gobject python3-pillow python3-requests
        gtk3 libnotify libayatana-appindicator-gtk3
    )

    if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        pkgs+=(grim slurp wl-clipboard)
        if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
            pkgs+=(spectacle)
        fi
    fi
    if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        pkgs+=(maim xdotool xclip)
    fi

    sudo dnf install -y "${pkgs[@]}" || {
        warn "Some packages may not be available. Installing core deps..."
        sudo dnf install -y python3 python3-pip python3-gobject python3-pillow python3-requests gtk3 libnotify
    }
}

install_deps_suse() {
    info "Installing system packages via zypper..."
    sudo zypper install -y python3 python3-pip python3-gobject python3-Pillow python3-requests \
        gtk3 libnotify-tools
    if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        sudo zypper install -y grim slurp wl-clipboard
        if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
            sudo zypper install -y spectacle
        fi
    fi
    if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        sudo zypper install -y maim xdotool xclip
    fi
}

install_deps_void() {
    info "Installing system packages via xbps..."
    sudo xbps-install -S python3 python3-pip python3-gobject python3-Pillow python3-requests \
        gtk+3 libnotify
    if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        sudo xbps-install -S grim slurp wl-clipboard
        if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
            sudo xbps-install -S spectacle
        fi
    fi
    if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
        sudo xbps-install -S maim xdotool xclip
    fi
}

case "$DISTRO" in
    arch)   install_deps_arch ;;
    debian) install_deps_debian ;;
    fedora) install_deps_fedora ;;
    suse)   install_deps_suse ;;
    void)   install_deps_void ;;
    *)
        warn "Unknown distro. Please install these manually:"
        echo "  Python 3.10+, PyGObject, Pillow, requests"
        echo "  GTK3, libnotify (notify-send)"
        if [ "$DISPLAY_SERVER" = "wayland" ] || [ "$DISPLAY_SERVER" = "both" ]; then
            echo "  Wayland: grim, slurp, wl-clipboard"
            if [[ "$DESKTOP_ENV" == *kde* || "$DESKTOP_ENV" == *plasma* ]]; then
                echo "  KDE Wayland: spectacle"
            fi
        fi
        if [ "$DISPLAY_SERVER" = "x11" ] || [ "$DISPLAY_SERVER" = "both" ]; then
            echo "  X11: maim, xdotool, xclip"
        fi
        echo ""
        read -p "Continue with pip install anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        ;;
esac

ok "System dependencies installed."
echo ""

# ── Install LinuxShot ──────────────────────────────────────────────

info "Installing LinuxShot..."
pip install --break-system-packages "$SCRIPT_DIR" 2>/dev/null || \
    pip install "$SCRIPT_DIR" 2>/dev/null || \
    pip install --user "$SCRIPT_DIR"

ok "LinuxShot installed."

# ── Install desktop file ──────────────────────────────────────────

DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
cp "$SCRIPT_DIR/resources/linuxshot.desktop" "$DESKTOP_DIR/"
# Update the Exec paths to use the installed binary
LINUXSHOT_BIN=$(which linuxshot 2>/dev/null || echo "linuxshot")
sed -i "s|Exec=linuxshot|Exec=$LINUXSHOT_BIN|g" "$DESKTOP_DIR/linuxshot.desktop"

ok "Desktop file installed to $DESKTOP_DIR"

# ── Create default config ─────────────────────────────────────────

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/linuxshot"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    "$LINUXSHOT_BIN" config --path > /dev/null 2>&1 || true
    info "Default config created at $CONFIG_DIR/config.json"
fi

# ── Done! ──────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║        LinuxShot installed successfully!     ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Quick start:${RESET}"
echo "    linuxshot region       — Capture a region"
echo "    linuxshot fullscreen   — Capture full screen"
echo "    linuxshot window       — Capture active window"
echo "    linuxshot tray         — Start system tray"
echo "    linuxshot gui          — Open settings window"
echo "    linuxshot check        — Verify dependencies"
echo ""
echo -e "  ${BOLD}Set up keyboard shortcuts:${RESET}"
echo "    In your DE settings, bind these commands:"
echo "    Print Screen        → linuxshot region"
echo "    Ctrl+Print Screen   → linuxshot fullscreen"
echo "    Alt+Print Screen    → linuxshot window"
echo ""
echo -e "  ${BOLD}Enable auto-upload:${RESET}"
echo "    linuxshot config --set auto_upload true"
echo ""
