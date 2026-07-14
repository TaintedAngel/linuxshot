"""KDE Plasma global shortcut registration.

Shortcuts are registered twice, on purpose:

1. Live, over DBus with KGlobalAccel, so they work immediately. The
   component id is plain "linuxshot" (no .desktop suffix) - that makes
   KGlobalAccel treat them as runtime app shortcuts and emit
   globalShortcutPressed signals to our tray process instead of trying
   to launch a desktop action.
2. In kglobalshortcutsrc, so they survive a re-login. We edit the file
   directly because kwriteconfig6 strips the commas KDE's
   "custom,default,friendly" value format requires.

Optionally disables Spectacle's PrtSc bindings so they don't fight ours.
"""

import os
import re
import shutil
import subprocess
import time
from datetime import datetime

KGLOBALSHORTCUTS_PATH = os.path.expanduser("~/.config/kglobalshortcutsrc")
DESKTOP_APPS_DIR = os.path.expanduser("~/.local/share/applications")
AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
ICONS_DIR = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")

SPECTACLE_DISABLED_ENTRIES = {
    "_k_friendly_name": "Spectacle",
    "_launch": "none,Print,Spectacle",
    "ActiveWindowScreenShot": "none,none,Capture Active Window",
    "CurrentMonitorScreenShot": "none,none,Capture Current Monitor",
    "FullScreenScreenShot": "none,none,Capture Full Screen",
    "OpenWithoutScreenshot": "none,none,Launch Spectacle",
    "RectangularRegionScreenShot": "none,none,Capture Rectangular Region",
    "WindowUnderCursorScreenShot": "none,none,Capture Window Under Cursor",
}


def _write_section(section_header: str, entries: dict[str, str]) -> None:
    """Replace (or append) one [section] of kglobalshortcutsrc in place,
    leaving every other section untouched.
    """
    lines: list[str] = []
    if os.path.isfile(KGLOBALSHORTCUTS_PATH):
        with open(KGLOBALSHORTCUTS_PATH) as f:
            lines = f.readlines()

    sec_start = sec_end = None
    header_re = re.compile(r"^\[.+\]")
    for i, line in enumerate(lines):
        if line.rstrip("\n") == section_header:
            sec_start = i
            sec_end = len(lines)
            for j in range(i + 1, len(lines)):
                if header_re.match(lines[j].rstrip("\n")):
                    sec_end = j
                    break
            break

    block = [section_header + "\n"]
    block += [f"{key}={value}\n" for key, value in entries.items()]
    block.append("\n")

    if sec_start is not None:
        lines[sec_start:sec_end] = block
    else:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.extend(block)

    with open(KGLOBALSHORTCUTS_PATH, "w") as f:
        f.writelines(lines)


def _backup_config() -> str | None:
    if not os.path.exists(KGLOBALSHORTCUTS_PATH):
        return None
    backup = f"{KGLOBALSHORTCUTS_PATH}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(KGLOBALSHORTCUTS_PATH, backup)
    return backup


def _get_shortcut_keys() -> tuple[str, str, str]:
    from .config import Config
    cfg = Config.get()
    return (
        cfg["shortcut_region"] or "Print",
        cfg["shortcut_fullscreen"] or "Ctrl+Print",
        cfg["shortcut_window"] or "Alt+Print",
    )


def _should_override_spectacle() -> bool:
    from .config import Config
    return bool(Config.get()["override_spectacle"])


def _key_string_to_qt_int(key_str: str) -> int | None:
    try:
        from PySide6.QtGui import QKeySequence
        ks = QKeySequence.fromString(key_str)
        if ks.count() > 0:
            return ks[0].toCombined()
    except Exception:
        pass
    return None


def _build_linuxshot_entries() -> dict[str, str]:
    region, fullscreen, window = _get_shortcut_keys()
    return {
        "_k_friendly_name": "LinuxShot",
        "CaptureRegion": f"{region},{region},Capture Region",
        "CaptureFullscreen": f"{fullscreen},{fullscreen},Capture Fullscreen",
        "CaptureWindow": f"{window},{window},Capture Active Window",
        "_launch": "none,none,LinuxShot",
    }


def register_shortcuts_dbus() -> list[str]:
    """Register shortcuts live with KGlobalAccel. Returns log lines."""
    msgs: list[str] = []
    try:
        import dbus
    except ImportError:
        msgs.append("warning: dbus-python not installed; shortcuts activate after re-login")
        return msgs

    try:
        bus = dbus.SessionBus()
        kga = bus.get_object("org.kde.kglobalaccel", "/kglobalaccel")
        iface = dbus.Interface(kga, "org.kde.KGlobalAccel")
    except Exception as e:
        msgs.append(f"warning: could not connect to KGlobalAccel: {e}")
        return msgs

    if _should_override_spectacle():
        try:
            iface.unregister(dbus.String("org.kde.spectacle.desktop"), dbus.String("_launch"))
            msgs.append("Released Spectacle's Print key")
        except Exception:
            pass

    # Older releases registered these under the .desktop component, which
    # never emits signals to us. Clear them out if present.
    for action in ("CaptureRegion", "CaptureFullscreen", "CaptureWindow"):
        try:
            iface.unregister(dbus.String("linuxshot.desktop"), dbus.String(action))
        except Exception:
            pass

    region, fullscreen, window = _get_shortcut_keys()
    shortcuts = [
        ("CaptureRegion", "Capture Region", region),
        ("CaptureFullscreen", "Capture Fullscreen", fullscreen),
        ("CaptureWindow", "Capture Active Window", window),
    ]
    for action, friendly, key_str in shortcuts:
        key_code = _key_string_to_qt_int(key_str)
        if key_code is None:
            msgs.append(f"warning: cannot parse key '{key_str}' for {action}")
            continue
        try:
            action_id = dbus.Array(["linuxshot", action, "LinuxShot", friendly], signature="s")
            keys = dbus.Array([dbus.Int32(key_code)], signature="i")
            iface.doRegister(action_id)
            # 0x02 = IsDefault: set the key even if something else holds it
            iface.setShortcut(action_id, keys, dbus.UInt32(0x02))
        except Exception as e:
            msgs.append(f"warning: shortcut {action}: {e}")

    return msgs


def _write_shortcut_config() -> None:
    # KDE's daemon may rewrite the file right after the DBus calls above;
    # give it a moment so our edit lands last.
    time.sleep(0.5)
    if _should_override_spectacle():
        _write_section("[services][org.kde.spectacle.desktop]", SPECTACLE_DISABLED_ENTRIES)
    _write_section("[services][linuxshot.desktop]", _build_linuxshot_entries())


def _rebuild_sycoca() -> bool:
    if not shutil.which("kbuildsycoca6"):
        return False
    try:
        subprocess.run(["kbuildsycoca6"], capture_output=True, timeout=30)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def install_desktop_file() -> None:
    os.makedirs(DESKTOP_APPS_DIR, exist_ok=True)
    linuxshot_bin = shutil.which("linuxshot") or "linuxshot"
    content = f"""\
[Desktop Entry]
Name=LinuxShot
Comment=ShareX-inspired screenshot and upload tool
Exec={linuxshot_bin} tray
Icon=linuxshot
Terminal=false
Type=Application
Categories=Utility;Graphics;
Keywords=screenshot;capture;upload;imgbb;screen;
StartupNotify=false
Actions=CaptureRegion;CaptureFullscreen;CaptureWindow;

[Desktop Action CaptureRegion]
Name=Capture Region
Exec={linuxshot_bin} region
Icon=linuxshot

[Desktop Action CaptureFullscreen]
Name=Capture Fullscreen
Exec={linuxshot_bin} fullscreen
Icon=linuxshot

[Desktop Action CaptureWindow]
Name=Capture Active Window
Exec={linuxshot_bin} window
Icon=linuxshot
"""
    with open(os.path.join(DESKTOP_APPS_DIR, "linuxshot.desktop"), "w") as f:
        f.write(content)


def install_autostart() -> None:
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    linuxshot_bin = shutil.which("linuxshot") or "linuxshot"
    content = f"""\
[Desktop Entry]
Name=LinuxShot
Comment=ShareX-inspired screenshot and upload tool
Exec={linuxshot_bin} tray
Icon=linuxshot
Terminal=false
Type=Application
X-KDE-autostart-after=panel
StartupNotify=false
NoDisplay=true
"""
    with open(os.path.join(AUTOSTART_DIR, "linuxshot.desktop"), "w") as f:
        f.write(content)


def install_icon() -> None:
    os.makedirs(ICONS_DIR, exist_ok=True)
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "resources", "linuxshot.svg")
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(ICONS_DIR, "linuxshot.svg"))
    if shutil.which("gtk-update-icon-cache"):
        icon_base = os.path.expanduser("~/.local/share/icons/hicolor")
        try:
            subprocess.run(
                ["gtk-update-icon-cache", "-f", "-t", icon_base],
                capture_output=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass


def reload_shortcuts() -> bool:
    """Nudge KGlobalAccel into re-reading its config."""
    for qdbus in ("qdbus6", "qdbus"):
        if not shutil.which(qdbus):
            continue
        try:
            for value in ("true", "false"):
                subprocess.run(
                    [qdbus, "org.kde.KGlobalAccel", "/kglobalaccel",
                     "blockGlobalShortcuts", value],
                    capture_output=True, timeout=5,
                )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return False


def setup_all() -> tuple[bool, list[str]]:
    """Run every setup step. Returns (success, log_lines)."""
    msgs: list[str] = []

    backup = _backup_config()
    if backup:
        msgs.append(f"Backed up shortcuts config to {backup}")

    try:
        install_icon()
        msgs.append("Installed tray icon")
    except Exception as e:
        msgs.append(f"warning: icon install failed: {e}")

    try:
        install_desktop_file()
        msgs.append("Installed linuxshot.desktop")
    except Exception as e:
        return False, [f"error: desktop file failed: {e}"]

    if _rebuild_sycoca():
        msgs.append("Rebuilt KDE service cache")
    else:
        msgs.append(
            "warning: kbuildsycoca6 not found; KDE may not see the desktop file until re-login")

    try:
        install_autostart()
        msgs.append("Installed autostart entry")
    except Exception as e:
        msgs.append(f"warning: autostart failed: {e}")

    msgs.extend(register_shortcuts_dbus())
    msgs.append("Registered shortcuts with KGlobalAccel")

    if reload_shortcuts():
        msgs.append("Reloaded KDE shortcuts")
    else:
        msgs.append("warning: could not reload; log out and back in to apply")

    try:
        _write_shortcut_config()
        msgs.append("Wrote shortcut config")
    except Exception as e:
        msgs.append(f"warning: config write failed: {e}")

    region, fullscreen, window = _get_shortcut_keys()
    msgs.append("")
    msgs.append("Shortcuts:")
    msgs.append(f"  {region:14s} -> region capture")
    msgs.append(f"  {fullscreen:14s} -> fullscreen capture")
    msgs.append(f"  {window:14s} -> active window capture")
    if _should_override_spectacle():
        msgs.append("  (Spectacle shortcuts disabled)")
    return True, msgs
