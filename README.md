# LinuxShot

**A ShareX-inspired screenshot and upload tool for Linux.**

Capture a region, fullscreen, or window with a single keypress, auto-upload to your choice of host, and get the link on your clipboard. Works on both **Wayland** and **X11**.

<p align="center">
  <img src="https://files.catbox.moe/v8qxc3.png" width="200" alt="Tray menu">
  &nbsp;&nbsp;
  <img src="https://files.catbox.moe/wjsoo7.png" width="350" alt="Settings">
</p>

## Features

- Region, fullscreen, and active window capture (PrtSc / Ctrl+PrtSc / Alt+PrtSc)
- Upload to **catbox.moe**, **0x0.st**, or **Imgur** (anonymous, link copied to clipboard)
- Global keyboard shortcuts on KDE Plasma via KGlobalAccel
- Desktop notifications on capture and upload
- System tray icon (PySide6/Qt) with context menu
- GUI settings window for shortcuts, upload, capture, and storage
- Capture history with CLI + GUI viewer
- Full CLI for scripting and keybinds
- Self-update: `linuxshot update`
- Works on Arch/CachyOS, Debian/Ubuntu, Fedora, openSUSE, Void

## Install

### Quick Install (recommended)

```bash
git clone https://github.com/TaintedAngel/linuxshot.git
cd linuxshot
chmod +x setup.sh
./setup.sh
```

The setup script will:
1. Detect your distro and display server
2. Install all system dependencies automatically
3. Install LinuxShot via pip
4. Set up the desktop file for your app launcher

### Manual Install

If you prefer to install manually:

```bash
# Arch / CachyOS
sudo pacman -S python python-pip python-gobject python-pillow python-requests \
    gtk3 libnotify grim slurp wl-clipboard libayatana-appindicator

# Debian / Ubuntu
sudo apt install python3 python3-pip python3-gi python3-pil python3-requests \
    gir1.2-gtk-3.0 libnotify-bin grim slurp wl-clipboard

# Fedora
sudo dnf install python3 python3-pip python3-gobject python3-pillow python3-requests \
    gtk3 libnotify grim slurp wl-clipboard

# Then install LinuxShot
pip install .
```

### For X11 users

Replace the Wayland tools with X11 equivalents:

```bash
# Arch / CachyOS
sudo pacman -S maim xdotool xclip

# Debian / Ubuntu
sudo apt install maim xdotool xclip

# Fedora
sudo dnf install maim xdotool xclip
```

## Usage

### CLI Commands

```
linuxshot region          Capture a selected region
linuxshot fullscreen      Capture the entire screen
linuxshot window          Capture the active window
linuxshot upload <file>   Upload a file
linuxshot upload-last     Upload the most recent capture
linuxshot history         Show recent capture history
linuxshot config          View/edit configuration
linuxshot tray            Start the system tray icon
linuxshot gui             Open the settings window
linuxshot setup           Register shortcuts, desktop file & autostart (KDE)
linuxshot update          Update to the latest version from GitHub
linuxshot check           Verify all dependencies
```

### System Tray

Start LinuxShot in the background with a tray icon:

```bash
linuxshot tray
```

Right-click the tray icon for quick actions: capture, upload, toggle auto-upload, open screenshots folder, etc.

To auto-start the tray on login, add `linuxshot tray` to your compositor/DE autostart config.

### GUI

```bash
linuxshot gui
```

Opens a window with three tabs:
- **Capture** - buttons for all capture modes
- **History** - past screenshots with upload status
- **Settings** - upload service, image format, Imgur client ID, etc.

## Keyboard Shortcuts

### KDE Plasma (automatic)

On KDE Plasma 6, LinuxShot can register global shortcuts automatically:

```bash
linuxshot setup
```

This registers PrtSc / Ctrl+PrtSc / Alt+PrtSc (replacing Spectacle), installs the desktop file, and sets up autostart. You can also configure shortcuts from the tray's **Settings** dialog.

### Other desktop environments (manual)

Bind these commands to your preferred keys:

#### Hyprland (`~/.config/hypr/hyprland.conf`)
```
bind = , Print, exec, linuxshot region
bind = CTRL, Print, exec, linuxshot fullscreen
bind = ALT, Print, exec, linuxshot window
```

#### Sway (`~/.config/sway/config`)
```
bindsym Print exec linuxshot region
bindsym Ctrl+Print exec linuxshot fullscreen
bindsym Alt+Print exec linuxshot window
```

#### i3 (`~/.config/i3/config`)
```
bindsym Print exec --no-startup-id linuxshot region
bindsym Ctrl+Print exec --no-startup-id linuxshot fullscreen
bindsym Alt+Print exec --no-startup-id linuxshot window
```

#### GNOME
```bash
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/']"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/ name 'LinuxShot Region'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/ command 'linuxshot region'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/ binding 'Print'
```

## Configuration

Config is stored at `~/.config/linuxshot/config.json`.

### View all settings

```bash
linuxshot config
```

### Common config tweaks

```bash
# Enable auto-upload to Imgur after every capture
linuxshot config --set auto_upload true

# Change image format to JPEG
linuxshot config --set image_format jpg

# Set a capture delay (seconds)
linuxshot config --set capture_delay 3

# Use your own Imgur Client ID
linuxshot config --set imgur_client_id YOUR_CLIENT_ID

# Change screenshot save directory
linuxshot config --set screenshot_dir /path/to/screenshots

# Reset everything to defaults
linuxshot config --reset
```

### Key config options

- `upload_service` - `catbox` (default), `0x0`, or `imgur`
- `auto_upload` - upload after every capture (default: false)
- `screenshot_dir` - save location (default: `~/Pictures/LinuxShot`)
- `image_format` - `png`, `jpg`, or `webp` (default: png)
- `copy_image_to_clipboard` - copy image to clipboard (default: true)
- `copy_url_to_clipboard` - copy URL after upload (default: true)
- `show_notification` - desktop notifications (default: true)
- `shortcut_region` / `shortcut_fullscreen` / `shortcut_window` - key bindings
- `override_spectacle` - replace Spectacle's PrtSc on KDE (default: true)

## Dependencies

### Wayland
- `grim` - screenshot capture
- `slurp` - region selection
- `wl-clipboard` - clipboard (wl-copy)

### X11
- `maim` - screenshot capture
- `xdotool` - active window detection
- `xclip` - clipboard

### Common
- Python 3.10+
- PySide6 (Qt6 tray and settings)
- PyGObject (GLib for DBus signal dispatch)
- dbus-python (shortcut signal listener)
- Pillow
- requests
- libnotify (notify-send)

Run `linuxshot check` to verify everything is installed.

## Uninstall

```bash
./uninstall.sh
```

Or manually:

```bash
pip uninstall linuxshot
rm ~/.local/share/applications/linuxshot.desktop
```

## Updating

```bash
linuxshot update
```

Or manually:

```bash
pip install --upgrade git+https://github.com/TaintedAngel/linuxshot.git
```

## License

GPL-3.0, same as ShareX.

## Contributing

Pull requests welcome! If you'd like to add features:

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Submit a PR

Ideas for contributions:
- Image annotation overlay
- Additional upload services (S3, custom HTTP, etc.)
- OCR via Tesseract
- Screen recording via wf-recorder/ffmpeg
- Theming support
