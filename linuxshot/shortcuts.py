"""KDE Plasma 6 global shortcut management for LinuxShot.

Writes directly to kglobalshortcutsrc (kwriteconfig6 strips the commas
that KDE's 3-part "custom,default,friendly" format requires).
Disables Spectacle's PrtSc binding and registers LinuxShot as the
screenshot handler.
"""

import os
import re
import shutil
import subprocess
from datetime import datetime

KGLOBALSHORTCUTS_PATH = os.path.expanduser("~/.config/kglobalshortcutsrc")
DESKTOP_APPS_DIR = os.path.expanduser("~/.local/share/applications")
AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
ICONS_DIR = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")


# ── Direct config file writer ──────────────────────────────────────


def _write_section(section_header: str, entries: dict[str, str]) -> None:
    """Write key=value pairs into a [section] of kglobalshortcutsrc.

    This edits the file in-place, preserving all other sections.
    *section_header* is the exact header line, e.g.
    ``[services][linuxshot.desktop]``.
    *entries* maps key names to their raw values (including commas).
    """
    path = KGLOBALSHORTCUTS_PATH
    lines: list[str] = []
    if os.path.isfile(path):
        with open(path, "r") as f:
            lines = f.readlines()

    # Locate existing section
    sec_start: int | None = None
    sec_end: int | None = None
    header_re = re.compile(r"^\[.+\]")
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped == section_header:
            sec_start = i
            # Find end of this section (next header or EOF)
            for j in range(i + 1, len(lines)):
                if header_re.match(lines[j].rstrip("\n")):
                    sec_end = j
                    break
            else:
                sec_end = len(lines)
            break

    # Build new section block
    new_block = [section_header + "\n"]
    for key, value in entries.items():
        new_block.append(f"{key}={value}\n")
    new_block.append("\n")

    if sec_start is not None:
        lines[sec_start:sec_end] = new_block
    else:
        # Append at end
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.extend(new_block)

    with open(path, "w") as f:
        f.writelines(lines)


def _backup_config() -> str | None:
    if os.path.exists(KGLOBALSHORTCUTS_PATH):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{KGLOBALSHORTCUTS_PATH}.bak.{ts}"
        shutil.copy2(KGLOBALSHORTCUTS_PATH, backup)
        return backup
    return None


# ── Individual setup steps ─────────────────────────────────────────


def _get_shortcut_keys() -> tuple[str, str, str]:
    """Read the configured shortcut key strings from LinuxShot config."""
    from .config import Config
    cfg = Config.get()
    return (
        cfg["shortcut_region"] or "Ctrl+Shift+4",
        cfg["shortcut_fullscreen"] or "Ctrl+Shift+3",
        cfg["shortcut_window"] or "Ctrl+Shift+5",
    )


def _should_override_spectacle() -> bool:
    from .config import Config
    return bool(Config.get()["override_spectacle"])


_SPECTACLE_DISABLED_ENTRIES = {
    "_k_friendly_name": "Spectacle",
    "_launch": "none,Print,Spectacle",
    "ActiveWindowScreenShot": "none,none,Capture Active Window",
    "CurrentMonitorScreenShot": "none,none,Capture Current Monitor",
    "FullScreenScreenShot": "none,none,Capture Full Screen",
    "OpenWithoutScreenshot": "none,none,Launch Spectacle",
    "RectangularRegionScreenShot": "none,none,Capture Rectangular Region",
    "WindowUnderCursorScreenShot": "none,none,Capture Window Under Cursor",
}


def _key_string_to_qt_int(key_str: str) -> int | None:
    """Convert a KDE key string like 'Ctrl+Shift+4' to a Qt key code int."""
    try:
        from PySide6.QtGui import QKeySequence
        ks = QKeySequence.fromString(key_str)
        if ks.count() > 0:
            return ks[0].toCombined()
    except Exception:
        pass
    return None


def _build_linuxshot_entries() -> dict[str, str]:
    """Build kglobalshortcutsrc entries using the configured keys."""
    region_key, fullscreen_key, window_key = _get_shortcut_keys()
    return {
        "_k_friendly_name": "LinuxShot",
        "CaptureRegion": f"{region_key},{region_key},Capture Region",
        "CaptureFullscreen": f"{fullscreen_key},{fullscreen_key},Capture Fullscreen",
        "CaptureWindow": f"{window_key},{window_key},Capture Active Window",
        "_launch": "none,none,LinuxShot",
    }


def _register_shortcuts_dbus() -> list[str]:
    """Register shortcuts with KGlobalAccel via DBus (immediate effect).

    Returns log messages.
    """
    msgs: list[str] = []
    try:
        import dbus
    except ImportError:
        msgs.append("⚠ dbus-python not installed - shortcuts won't activate until re-login")
        return msgs

    try:
        bus = dbus.SessionBus()
        kga = bus.get_object('org.kde.kglobalaccel', '/kglobalaccel')
        iface = dbus.Interface(kga, 'org.kde.KGlobalAccel')
    except Exception as e:
        msgs.append(f"⚠ Could not connect to KGlobalAccel DBus: {e}")
        return msgs

    # Unregister Spectacle only if the user opted in
    if _should_override_spectacle():
        try:
            iface.unregister(
                dbus.String("org.kde.spectacle.desktop"),
                dbus.String("_launch"),
            )
            msgs.append("✓ Unregistered Spectacle's Print key via DBus")
        except Exception:
            pass

    region_key, fullscreen_key, window_key = _get_shortcut_keys()
    shortcuts = [
        ("CaptureRegion", "Capture Region", region_key),
        ("CaptureFullscreen", "Capture Fullscreen", fullscreen_key),
        ("CaptureWindow", "Capture Active Window", window_key),
    ]

    # Clean up old .desktop component if it exists (was incorrectly registered
    # as a service shortcut which doesn't emit signals to our process)
    try:
        iface.unregister(
            dbus.String("linuxshot.desktop"),
            dbus.String("CaptureRegion"),
        )
        iface.unregister(
            dbus.String("linuxshot.desktop"),
            dbus.String("CaptureFullscreen"),
        )
        iface.unregister(
            dbus.String("linuxshot.desktop"),
            dbus.String("CaptureWindow"),
        )
    except Exception:
        pass  # May not exist

    for action_name, friendly_name, key_str in shortcuts:
        key_code = _key_string_to_qt_int(key_str)
        if key_code is None:
            msgs.append(f"⚠ Cannot parse key '{key_str}' for {action_name}")
            continue
        try:
            # Use "linuxshot" (not .desktop) so KGlobalAccel treats these as
            # runtime app shortcuts and emits globalShortcutPressed signals
            # instead of trying to launch a desktop action.
            action_id = dbus.Array([
                "linuxshot", action_name, "LinuxShot", friendly_name
            ], signature='s')
            keys = dbus.Array([dbus.Int32(key_code)], signature='i')
            iface.doRegister(action_id)
            # setShortcut flags: 0x02 = IsDefault (force set even if exists)
            iface.setShortcut(action_id, keys, dbus.UInt32(0x02))
        except Exception as e:
            msgs.append(f"⚠ DBus shortcut {action_name}: {e}")

    return msgs


def _write_shortcut_config() -> None:
    """Write LinuxShot (and optionally Spectacle) sections to the config file.

    Must be called AFTER DBus operations so KDE's daemon doesn't overwrite.
    """
    import time
    time.sleep(0.5)  # Let KDE finish any config writes triggered by DBus
    if _should_override_spectacle():
        _write_section("[services][org.kde.spectacle.desktop]", _SPECTACLE_DISABLED_ENTRIES)
    _write_section("[services][linuxshot.desktop]", _build_linuxshot_entries())


def _rebuild_sycoca() -> bool:
    """Rebuild KDE's service cache so it knows about linuxshot.desktop."""
    if shutil.which("kbuildsycoca6"):
        try:
            subprocess.run(["kbuildsycoca6"], capture_output=True, timeout=30)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return False


def install_desktop_file() -> None:
    """Install linuxshot.desktop with Actions into ~/.local/share/applications."""
    os.makedirs(DESKTOP_APPS_DIR, exist_ok=True)
    # Resolve the linuxshot binary so KDE can execute it
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
Keywords=screenshot;capture;upload;imgur;screen;
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
    """Install autostart entry so the tray starts on login."""
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
    """Copy the bundled SVG icon into the hicolor icon theme."""
    os.makedirs(ICONS_DIR, exist_ok=True)
    src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "icons", "linuxshot.svg",
    )
    dst = os.path.join(ICONS_DIR, "linuxshot.svg")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
    # refresh icon cache
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
    """Ask KDE to pick up the changed shortcut config."""
    for qdbus in ("qdbus6", "qdbus"):
        if shutil.which(qdbus):
            try:
                subprocess.run(
                    [qdbus, "org.kde.KGlobalAccel", "/kglobalaccel",
                     "blockGlobalShortcuts", "true"],
                    capture_output=True, timeout=5,
                )
                subprocess.run(
                    [qdbus, "org.kde.KGlobalAccel", "/kglobalaccel",
                     "blockGlobalShortcuts", "false"],
                    capture_output=True, timeout=5,
                )
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    return False


# ── One-shot full setup ────────────────────────────────────────────


def setup_all() -> tuple[bool, list[str]]:
    """Run every setup step. Returns (success, log_lines)."""
    msgs: list[str] = []

    backup = _backup_config()
    if backup:
        msgs.append(f"Backed up shortcuts config → {backup}")

    try:
        install_icon()
        msgs.append("✓ Installed tray icon")
    except Exception as e:
        msgs.append(f"⚠ Icon install failed: {e}")

    try:
        install_desktop_file()
        msgs.append("✓ Installed linuxshot.desktop (with Actions)")
    except Exception as e:
        return False, [f"✗ Desktop file failed: {e}"]

    # Rebuild KDE service cache so it discovers linuxshot.desktop
    if _rebuild_sycoca():
        msgs.append("✓ Rebuilt KDE service cache (kbuildsycoca6)")
    else:
        msgs.append("⚠ kbuildsycoca6 not found - KDE may not see new desktop file until re-login")

    try:
        install_autostart()
        msgs.append("✓ Installed autostart entry")
    except Exception as e:
        msgs.append(f"⚠ Autostart failed: {e}")

    # Step 1: DBus registration (live effect, but may cause KDE to rewrite config)
    dbus_msgs = _register_shortcuts_dbus()
    msgs.extend(dbus_msgs)
    msgs.append("✓ Registered LinuxShot shortcuts via DBus")

    if reload_shortcuts():
        msgs.append("✓ Reloaded KDE shortcuts")
    else:
        msgs.append("⚠ Could not reload - log out and back in to apply")

    # Step 2: Write config file LAST so KDE's daemon doesn't overwrite it
    try:
        _write_shortcut_config()
        msgs.append("✓ Wrote shortcut config")
    except Exception as e:
        msgs.append(f"⚠ Config write failed: {e}")

    region_key, fullscreen_key, window_key = _get_shortcut_keys()
    msgs.append("")
    msgs.append("Shortcuts:")
    msgs.append(f"  {region_key:14s} → Region capture")
    msgs.append(f"  {fullscreen_key:14s} → Fullscreen capture")
    msgs.append(f"  {window_key:14s} → Active window capture")
    if _should_override_spectacle():
        msgs.append("  (Spectacle shortcuts disabled)")
    return True, msgs
