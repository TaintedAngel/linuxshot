"""Command line interface.

Heavy imports (Qt, DBus) are deferred into the command handlers so that
`linuxshot region` from a keybind stays fast.
"""

import argparse
import json
import sys

from . import __app_name__, __version__
from .capture import CaptureMode


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        # Bare `linuxshot` starts the tray, matching how ShareX lives in
        # the notification area.
        return cmd_tray(args)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linuxshot",
        description=f"{__app_name__} {__version__} - ShareX-inspired screenshot tool for Linux",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{__app_name__} {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    for mode in ("region", "fullscreen", "window"):
        p = sub.add_parser(mode, help=f"Capture {mode}")
        p.set_defaults(func=cmd_capture, mode=mode)

    p = sub.add_parser("edit", help="Annotate an image in the editor")
    p.add_argument("file", help="Path to the image to edit")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("ocr", help="Capture a region and copy its text (tesseract)")
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser("pick-color", help="Pick a pixel color from the screen")
    p.set_defaults(func=cmd_pick_color)

    p = sub.add_parser("pin", help="Pin an image to the screen, always on top")
    p.add_argument("file", nargs="?", default="",
                   help="Image to pin (default: the most recent capture)")
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("upload", help="Upload a file")
    p.add_argument("file", help="Path to the file to upload")
    p.add_argument("-s", "--service", metavar="NAME",
                   help="Destination (imgbb, imgur, catbox, 0x0, custom); "
                        "defaults to the upload_service config key")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("upload-last", help="Upload the most recent capture")
    p.set_defaults(func=cmd_upload_last)

    p = sub.add_parser("history", help="Show capture history")
    p.add_argument("-n", "--limit", type=int, default=10, help="Number of entries to show")
    p.add_argument("--clear", action="store_true", help="Clear all history")
    p.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("config", help="View or edit configuration")
    p.add_argument("--path", action="store_true", help="Show config file path")
    p.add_argument("--reset", action="store_true", help="Reset to defaults")
    p.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a config value")
    p.add_argument("--get", metavar="KEY", help="Get a config value")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("tray", help="Start the system tray icon")
    p.set_defaults(func=cmd_tray)

    p = sub.add_parser("gui", help="Open the main window")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser(
        "setup",
        help="Register shortcuts, install desktop file and autostart (KDE)",
    )
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("update", help="Update LinuxShot from GitHub")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("check", help="Check system dependencies")
    p.set_defaults(func=cmd_check)

    return parser


def cmd_capture(args) -> int:
    from .app import App
    from .config import Config

    editor = None
    if Config.get()["open_editor_after_capture"]:
        try:
            from .gui.editor import run_editor_standalone
            editor = run_editor_standalone
        except ImportError:
            pass  # capture still works without Qt, just unannotated
    return 0 if App().run_capture(CaptureMode(args.mode), editor=editor) else 1


def cmd_edit(args) -> int:
    import os

    if not os.path.isfile(args.file):
        print(f"error: no such file: {args.file}", file=sys.stderr)
        return 1
    try:
        from .gui.editor import run_editor_standalone
    except ImportError as e:
        print(f"error: the editor requires PySide6: {e}", file=sys.stderr)
        return 1
    outcome = run_editor_standalone(args.file)
    if outcome == "done":
        print(f"Saved: {args.file}")
    return 0


def cmd_ocr(args) -> int:
    from .app import App
    return 0 if App().run_ocr() else 1


def cmd_pick_color(args) -> int:
    from . import clipboard, notify
    from .colorpick import pick_color

    color = pick_color()
    if not color:
        print("error: color picking cancelled or unsupported on this desktop.\n"
              "KDE/GNOME need xdg-desktop-portal; wlroots compositors need "
              "hyprpicker.", file=sys.stderr)
        return 1
    print(color)
    if clipboard.copy_text(color):
        notify.send("Color picked", f"{color} copied to clipboard.")
    return 0


def cmd_pin(args) -> int:
    import os

    filepath = args.file
    if not filepath:
        from .history import History
        entries = History().get_entries(limit=1)
        if not entries:
            print("error: no captures in history to pin.", file=sys.stderr)
            return 1
        filepath = entries[0].filepath
    if not os.path.isfile(filepath):
        print(f"error: no such file: {filepath}", file=sys.stderr)
        return 1
    try:
        from .gui.pin import run_pin_standalone
    except ImportError as e:
        print(f"error: pinning requires PySide6: {e}", file=sys.stderr)
        return 1
    run_pin_standalone(filepath)
    return 0


def cmd_upload(args) -> int:
    from .app import App
    return 0 if App().upload_file(args.file, service=args.service) else 1


def cmd_upload_last(args) -> int:
    from .app import App
    return 0 if App().upload_last() else 1


def cmd_history(args) -> int:
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

    for entry in entries:
        marker = "^" if entry.uploaded else "-"
        size_kb = entry.filesize / 1024
        print(f"  {marker} [{entry.timestamp[:19]}] {entry.filepath} ({size_kb:.0f} KB)")
        if entry.upload_url:
            print(f"      {entry.upload_url}")
    print(f"\n  Total: {history.count} captures")
    return 0


def cmd_config(args) -> int:
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
        key, raw = args.set
        if not config.is_known_key(key):
            print(f"Unknown key: {key}", file=sys.stderr)
            print("Run 'linuxshot config' to list valid keys.", file=sys.stderr)
            return 1
        try:
            value = json.loads(raw)  # parses bools/ints; strings fall through
        except json.JSONDecodeError:
            value = raw
        config[key] = value
        config.save()
        print(f"Set {key} = {value!r}")
        return 0

    if args.get:
        if not config.is_known_key(args.get):
            print(f"Unknown key: {args.get}", file=sys.stderr)
            return 1
        print(f"{args.get} = {config[args.get]!r}")
        return 0

    print(f"Config file: {config.path}\n")
    for key, value in sorted(config.data.items()):
        print(f"  {key} = {value!r}")
    return 0


def cmd_tray(args) -> int:
    try:
        from .gui.tray import run_tray
    except ImportError as e:
        print(f"error: the tray requires PySide6: {e}", file=sys.stderr)
        print("Install it with: pip install PySide6", file=sys.stderr)
        return 1
    run_tray()
    return 0


def cmd_gui(args) -> int:
    try:
        from .gui.main_window import run_gui
    except ImportError as e:
        print(f"error: the GUI requires PySide6: {e}", file=sys.stderr)
        print("Install it with: pip install PySide6", file=sys.stderr)
        return 1
    run_gui()
    return 0


def cmd_setup(args) -> int:
    from .shortcuts import setup_all

    success, messages = setup_all()
    for msg in messages:
        print(msg)
    return 0 if success else 1


def cmd_update(args) -> int:
    import subprocess

    print("Updating LinuxShot from GitHub...")
    result = subprocess.run([
        sys.executable, "-m", "pip", "install", "--upgrade",
        "git+https://github.com/TaintedAngel/linuxshot.git",
    ])
    if result.returncode == 0:
        print("\nLinuxShot updated. Restart the tray to apply: linuxshot tray")
    else:
        print("\nUpdate failed. Try manually:", file=sys.stderr)
        print("  pip install --upgrade git+https://github.com/TaintedAngel/linuxshot.git",
              file=sys.stderr)
    return result.returncode


def cmd_check(args) -> int:
    from .capture import detect_wayland_backend
    from .utils import check_dependencies, get_display_server

    ds = get_display_server()
    print(f"Display server: {ds.value}\n")

    deps = check_dependencies()

    if ds.value == "wayland":
        backend = detect_wayland_backend()
        print(f"Wayland backend: {backend}\n")
        print("Wayland tools:")
        _print_dep("spectacle", deps["spectacle"], "KDE screenshot tool")
        _print_dep("gnome-screenshot", deps["gnome-screenshot"], "GNOME screenshot tool")
        _print_dep("grim", deps["grim"], "wlroots screenshot capture")
        _print_dep("slurp", deps["slurp"], "wlroots region selection")
        _print_dep("wl-copy", deps["wl-copy"], "clipboard (wl-clipboard)")
        _print_dep("wl-paste", deps["wl-paste"], "clipboard image retrieval")
        required = {
            "spectacle": ["spectacle", "wl-copy", "wl-paste"],
            "gnome-screenshot": ["gnome-screenshot", "wl-copy"],
            "grim": ["grim", "slurp", "wl-copy"],
        }.get(backend)
    else:
        print("X11 tools:")
        _print_dep("maim", deps["maim"], "screenshot capture")
        _print_dep("xdotool", deps["xdotool"], "window detection")
        _print_dep("xclip", deps["xclip"], "clipboard")
        required = ["maim", "xclip"]

    print("\nCommon tools:")
    _print_dep("notify-send", deps["notify-send"], "desktop notifications (libnotify)")

    print("\nOptional tools:")
    _print_dep("tesseract", deps["tesseract"], "OCR (linuxshot ocr)")
    _print_dep("hyprpicker", deps["hyprpicker"], "color picker fallback on wlroots")

    print("\nPython packages:")
    for name, module in (("requests", "requests"), ("PySide6", "PySide6"),
                         ("PyGObject", "gi"), ("dbus-python", "dbus")):
        _print_dep(name, _importable(module), "")

    print()
    if required is None:
        print("No usable Wayland screenshot backend found.")
        print("Run ./setup.sh to install dependencies.")
        return 1

    missing = [d for d in required if not deps[d]]
    if missing:
        print(f"Missing required: {', '.join(missing)}")
        print("Run ./setup.sh to install dependencies.")
        return 1

    print("All required dependencies are installed.")
    return 0


def _print_dep(name: str, available: bool, desc: str) -> None:
    if available:
        status = "\033[32mok\033[0m     "
    else:
        status = "\033[31mmissing\033[0m"
    print(f"  {status} {name}" + (f" - {desc}" if desc else ""))


def _importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.exit(main())
