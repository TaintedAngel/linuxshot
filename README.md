# LinuxShot

**A ShareX-inspired screenshot and upload tool for Linux.**

LinuxShot brings the core ShareX workflow to Linux — capture a region, fullscreen, or window, auto-upload to Imgur, and copy the link to your clipboard, all with a single keypress. Works on both **Wayland** and **X11**.

## Features

- **Region capture** — select any area of your screen (like ShareX's Print Screen)
- **Fullscreen capture** — grab the entire screen instantly
- **Active window capture** — capture just the focused window (Hyprland, Sway, X11)
- **Auto-upload to Imgur** — anonymous upload, link copied to clipboard
- **Desktop notifications** — get notified on capture and upload
- **System tray** — quick-access menu, just like ShareX
- **GUI settings window** — configure everything visually
- **Capture history** — browse and manage past screenshots
- **CLI interface** — scriptable, perfect for keybinds
- **Multi-distro support** — Arch/CachyOS, Debian/Ubuntu, Fedora, openSUSE, Void

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
linuxshot upload <file>   Upload a file to Imgur
linuxshot upload-last     Upload the most recent capture
linuxshot history         Show capture history
linuxshot config          View/edit configuration
linuxshot tray            Start the system tray icon
linuxshot gui             Open the settings window
linuxshot check           Verify all dependencies
```

### System Tray

Start LinuxShot in the background with a tray icon:

```bash
linuxshot tray
```

Right-click the tray icon for quick actions — capture, upload, toggle auto-upload, open screenshots folder, etc.

To auto-start the tray on login, add `linuxshot tray` to your compositor/DE autostart config.

### GUI

```bash
linuxshot gui
```

Opens a window with three tabs:
- **Capture** — quick-action buttons for all capture modes
- **History** — browse past screenshots with upload status
- **Settings** — toggle features, set Imgur client ID, image format, etc.

## Keyboard Shortcuts

LinuxShot is designed to be bound to keyboard shortcuts, just like ShareX. Set these up in your desktop environment:

### Hyprland

Add to `~/.config/hypr/hyprland.conf`:

```
bind = , Print, exec, linuxshot region
bind = CTRL, Print, exec, linuxshot fullscreen
bind = ALT, Print, exec, linuxshot window
```

### Sway

Add to `~/.config/sway/config`:

```
bindsym Print exec linuxshot region
bindsym Ctrl+Print exec linuxshot fullscreen
bindsym Alt+Print exec linuxshot window
```

### KDE Plasma

1. System Settings → Shortcuts → Custom Shortcuts
2. Add new → Global Shortcut → Command/URL
3. Set trigger to Print Screen, action to `linuxshot region`
4. Repeat for Ctrl+Print Screen → `linuxshot fullscreen`
5. Repeat for Alt+Print Screen → `linuxshot window`

### GNOME

```bash
# Region capture on Print Screen
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/']"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/ name 'LinuxShot Region'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/ command 'linuxshot region'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linuxshot-region/ binding 'Print'
```

### i3

Add to `~/.config/i3/config`:

```
bindsym Print exec --no-startup-id linuxshot region
bindsym Ctrl+Print exec --no-startup-id linuxshot fullscreen
bindsym Alt+Print exec --no-startup-id linuxshot window
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

### All config options

| Option | Default | Description |
|---|---|---|
| `screenshot_dir` | `~/Pictures/LinuxShot` | Where screenshots are saved |
| `image_format` | `png` | Image format: png, jpg, webp |
| `jpg_quality` | `95` | JPEG quality (1-100) |
| `auto_upload` | `false` | Upload to Imgur after every capture |
| `copy_image_to_clipboard` | `true` | Copy screenshot image to clipboard |
| `copy_url_to_clipboard` | `true` | Copy Imgur URL to clipboard after upload |
| `show_notification` | `true` | Show desktop notification |
| `capture_delay` | `0` | Seconds to wait before capturing |
| `imgur_client_id` | *(built-in)* | Your Imgur API client ID |
| `save_history` | `true` | Track capture history |
| `max_history_entries` | `1000` | Max history entries to keep |

## Dependencies

### Wayland
- `grim` — screenshot capture
- `slurp` — region selection
- `wl-clipboard` — clipboard (wl-copy)

### X11
- `maim` — screenshot capture
- `xdotool` — active window detection
- `xclip` — clipboard

### Common
- Python 3.10+
- PyGObject (GTK3 bindings)
- Pillow
- requests
- libnotify (notify-send)
- AppIndicator3 or AyatanaAppIndicator3 (for system tray)

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

## ShareX Feature Comparison

| ShareX Feature | LinuxShot | Notes |
|---|---|---|
| Region capture | ✅ | via grim+slurp / maim |
| Fullscreen capture | ✅ | |
| Window capture | ✅ | Hyprland, Sway, X11 |
| Capture delay | ✅ | Configurable |
| Auto-upload (Imgur) | ✅ | Anonymous upload |
| Copy to clipboard | ✅ | Image + URL |
| Desktop notification | ✅ | |
| System tray | ✅ | AppIndicator + StatusIcon fallback |
| Capture history | ✅ | JSON-based with CLI + GUI viewer |
| Settings GUI | ✅ | GTK3 window |
| Image annotation | ❌ | Planned |
| Screen recording | ❌ | Use OBS or wf-recorder |
| GIF capture | ❌ | Use peek or gifski |
| OCR | ❌ | Planned |
| Multiple upload services | ❌ | Imgur only (extensible) |
| Scrolling capture | ❌ | Not feasible on Linux |

## License

GPL-3.0 — same as ShareX.

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
