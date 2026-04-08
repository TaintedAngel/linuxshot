"""LinuxShot CLI entry point.

Usage:
    linuxshot region          Capture a selected region (like ShareX Print Screen)
    linuxshot fullscreen      Capture the full screen (like ShareX Ctrl+Print Screen)
    linuxshot window          Capture the active window (like ShareX Alt+Print Screen)
    linuxshot upload <file>   Upload a file to ImgBB
    linuxshot upload-last     Upload the most recent capture
    linuxshot history         Show recent capture history
    linuxshot config          Show/edit configuration
    linuxshot tray            Start the system tray daemon
    linuxshot gui             Open the main window
    linuxshot check           Check system dependencies
"""

import argparse
import json
import sys

from . import __app_name__, __version__
from .capture import CaptureMode


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="linuxshot",
        description=f"{__app_name__} v{__version__} - ShareX-inspired screenshot tool for Linux",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{__app_name__} {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── Capture commands ───────────────────────────────────────────────
    subparsers.add_parser("region", help="Capture a selected screen region")
    subparsers.add_parser("fullscreen", help="Capture the entire screen")
    subparsers.add_parser("window", help="Capture the active window")

    # ── Upload commands ────────────────────────────────────────────────
    upload_parser = subparsers.add_parser("upload", help="Upload a file to ImgBB")
    upload_parser.add_argument("file", help="Path to the file to upload")

    subparsers.add_parser("upload-last", help="Upload the most recent capture")

    # ── History ────────────────────────────────────────────────────────
    history_parser = subparsers.add_parser("history", help="Show capture history")
    history_parser.add_argument(
        "-n", "--limit", type=int, default=10, help="Number of entries to show"
    )
    history_parser.add_argument(
        "--clear", action="store_true", help="Clear all history"
    )
    history_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )

    # ── Config ─────────────────────────────────────────────────────────
    config_parser = subparsers.add_parser("config", help="View or edit configuration")
    config_parser.add_argument("--path", action="store_true", help="Show config file path")
    config_parser.add_argument("--reset", action="store_true", help="Reset to defaults")
    config_parser.add_argument(
        "--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a config value"
    )
    config_parser.add_argument(
        "--get", metavar="KEY", help="Get a config value"
    )

    # ── Tray / GUI ─────────────────────────────────────────────────────
    subparsers.add_parser("tray", help="Start the system tray icon")
    subparsers.add_parser("gui", help="Open the main LinuxShot window")

    # ── Setup & Auth ───────────────────────────────────────────────────
    subparsers.add_parser(
        "setup",
        help="Configure PrtSc shortcuts, disable Spectacle, install tray icon & autostart",
    )

    # ── Update ──────────────────────────────────────────────────────────
    subparsers.add_parser(
        "update",
        help="Update LinuxShot to the latest version from GitHub",
    )

    # ── Diagnostics ────────────────────────────────────────────────────
    subparsers.add_parser("check", help="Check system dependencies")

    args = parser.parse_args()

    if args.command is None:
        # No command given → start the tray daemon (like ShareX)
        return _cmd_tray()

    # ── Route commands ─────────────────────────────────────────────────

    if args.command in ("region", "fullscreen", "window"):
        return _cmd_capture(args.command)

    if args.command == "upload":
        return _cmd_upload(args.file)

    if args.command == "upload-last":
        return _cmd_upload_last()

    if args.command == "history":
        return _cmd_history(args)

    if args.command == "config":
        return _cmd_config(args)

    if args.command == "tray":
        return _cmd_tray()

    if args.command == "gui":
        return _cmd_gui()

    if args.command == "check":
        return _cmd_check()

    if args.command == "setup":
        return _cmd_setup()

    if args.command == "update":
        return _cmd_update()

    parser.print_help()
    return 0


# ── Command implementations ───────────────────────────────────────────


def _cmd_capture(mode_name: str) -> int:
    from .app import App

    mode_map = {
        "region": CaptureMode.REGION,
        "fullscreen": CaptureMode.FULLSCREEN,
        "window": CaptureMode.WINDOW,
    }
    app = App()
    success = app.run_capture(mode_map[mode_name])
    return 0 if success else 1


def _cmd_upload(filepath: str) -> int:
    from .app import App

    app = App()
    url = app.upload_file(filepath)
    return 0 if url else 1


def _cmd_upload_last() -> int:
    from .app import App

    app = App()
    url = app.upload_last()
    return 0 if url else 1


def _cmd_history(args) -> int:
    from .history import History

    history = History()

    if args.clear:
        history.clear()
        print("History cleared.")
        return 0

    entries = history.get_entries(limit=args.limit)
    if not entries:
        print("No captures in history.")
        return 0

    if args.as_json:
        from dataclasses import asdict
        print(json.dumps([asdict(e) for e in entries], indent=2))
        return 0

    # Pretty print
    for i, entry in enumerate(entries, 1):
        status = "↑" if entry.uploaded else "•"
        size_kb = entry.filesize / 1024
        print(f"  {status} [{entry.timestamp[:19]}] {entry.filepath} ({size_kb:.0f} KB)")
        if entry.upload_url:
            print(f"    URL: {entry.upload_url}")

    print(f"\n  Total: {history.count} captures")
    return 0


def _cmd_config(args) -> int:
    from .config import Config

    config = Config.get()

    if args.path:
        print(config.path)
        return 0

    if args.reset:
        config.reset()
        print(f"Config reset to defaults. ({config.path})")
        return 0

    if args.set:
        key, value = args.set
        # Try to parse as JSON value (handles bools, ints, etc.)
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass  # Keep as string
        config[key] = value
        config.save()
        print(f"Set {key} = {value!r}")
        return 0

    if args.get:
        value = config[args.get]
        if value is None:
            print(f"Unknown key: {args.get}", file=sys.stderr)
            return 1
        print(f"{args.get} = {value!r}")
        return 0

    # Show all config
    print(f"Config file: {config.path}\n")
    for key, value in sorted(config.data.items()):
        print(f"  {key} = {value!r}")

    return 0


def _cmd_tray() -> int:
    try:
        from .tray import run_tray
        run_tray()
        return 0
    except ImportError as e:
        print(f"Error: System tray requires PySide6: {e}", file=sys.stderr)
        print("Install with: pip install PySide6", file=sys.stderr)
        return 1


def _cmd_gui() -> int:
    try:
        from .ui.main_window import run_gui
        run_gui()
        return 0
    except ImportError as e:
        print(f"Error: GUI requires PySide6 or GTK3: {e}", file=sys.stderr)
        print("Install with: pip install PySide6", file=sys.stderr)
        return 1


def _cmd_setup() -> int:
    from .shortcuts import setup_all

    success, messages = setup_all()
    for msg in messages:
        print(msg)
    return 0 if success else 1


def _cmd_update() -> int:
    import subprocess
    print("Updating LinuxShot from GitHub...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade",
         "git+https://github.com/TaintedAngel/linuxshot.git"],
        capture_output=False,
    )
    if result.returncode == 0:
        print("\nLinuxShot updated successfully!")
        print("Restart the tray to apply changes: linuxshot tray")
    else:
        print("\nUpdate failed. Try manually:", file=sys.stderr)
        print("  pip install --upgrade git+https://github.com/TaintedAngel/linuxshot.git", file=sys.stderr)
    return result.returncode


def _cmd_check() -> int:
    from .utils import check_dependencies, get_display_server
    from .capture import _detect_wayland_backend

    ds = get_display_server()
    print(f"Display server: {ds.value}\n")

    deps = check_dependencies()

    if ds.value == "wayland":
        backend = _detect_wayland_backend()
        print(f"Wayland backend: {backend}\n")
        print("Wayland tools:")
        _print_dep("  spectacle", deps["spectacle"], "KDE screenshot tool")
        _print_dep("  gnome-screenshot", deps["gnome-screenshot"], "GNOME screenshot tool")
        _print_dep("  grim", deps["grim"], "wlroots screenshot capture")
        _print_dep("  slurp", deps["slurp"], "wlroots region selection")
        _print_dep("  wl-copy", deps["wl-copy"], "Clipboard (wl-clipboard)")
        _print_dep("  wl-paste", deps["wl-paste"], "Clipboard image retrieval")
    else:
        print("X11 tools:")
        _print_dep("  maim", deps["maim"], "Screenshot capture")
        _print_dep("  xdotool", deps["xdotool"], "Window detection")
        _print_dep("  xclip", deps["xclip"], "Clipboard")

    print("\nCommon tools:")
    _print_dep("  notify-send", deps["notify-send"], "Desktop notifications (libnotify)")

    # Check Python packages
    print("\nPython packages:")
    _check_python_pkg("  requests", "requests")
    _check_python_pkg("  Pillow", "PIL")
    _check_python_pkg("  PyGObject", "gi")

    # Summary
    all_ok = True
    if ds.value == "wayland":
        backend = _detect_wayland_backend()
        if backend == "spectacle":
            required = ["spectacle", "wl-copy", "wl-paste"]
        elif backend == "gnome-screenshot":
            required = ["gnome-screenshot", "wl-copy"]
        elif backend == "grim":
            required = ["grim", "slurp", "wl-copy"]
        else:
            required = []
            all_ok = False
    else:
        required = ["maim", "xclip"]
    for dep in required:
        if not deps[dep]:
            all_ok = False

    print()
    if all_ok:
        print("All required dependencies are installed!")
    else:
        missing = [d for d in required if not deps[d]]
        print(f"Missing required: {', '.join(missing)}")
        print("Run ./setup.sh to install dependencies.")

    return 0 if all_ok else 1


def _print_dep(name: str, available: bool, desc: str) -> None:
    status = "✓" if available else "✗"
    color = "\033[32m" if available else "\033[31m"
    reset = "\033[0m"
    print(f"  {color}{status}{reset} {name} - {desc}")


def _check_python_pkg(name: str, import_name: str) -> None:
    try:
        __import__(import_name)
        available = True
    except ImportError:
        available = False
    _print_dep(name, available, "")


if __name__ == "__main__":
    sys.exit(main())
