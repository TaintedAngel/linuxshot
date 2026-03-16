"""Main GUI window for LinuxShot - settings, history, and quick actions."""

import os
import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango, GLib

from ..app import App
from ..capture import CaptureMode
from ..config import Config
from ..history import History


class MainWindow(Gtk.Window):
    """Main LinuxShot window with tabs for actions, history, and settings."""

    def __init__(self):
        super().__init__(title="LinuxShot")
        self.set_default_size(700, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name("camera-photo")

        self.app = App()
        self.config = Config.get()
        self.history = History()

        self._build_ui()

    def _build_ui(self) -> None:
        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("LinuxShot")
        header.set_subtitle("ShareX-inspired screenshot tool")
        self.set_titlebar(header)

        # Notebook (tabs)
        notebook = Gtk.Notebook()
        vbox.pack_start(notebook, True, True, 0)

        # Tab 1: Quick Actions
        notebook.append_page(self._build_actions_tab(), Gtk.Label(label="Capture"))

        # Tab 2: History
        notebook.append_page(self._build_history_tab(), Gtk.Label(label="History"))

        # Tab 3: Settings
        notebook.append_page(self._build_settings_tab(), Gtk.Label(label="Settings"))

    # ── Tab: Quick Actions ─────────────────────────────────────────

    def _build_actions_tab(self) -> Gtk.Widget:
        grid = Gtk.Grid()
        grid.set_row_spacing(12)
        grid.set_column_spacing(12)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        grid.set_margin_start(20)
        grid.set_margin_end(20)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)

        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Screenshot Capture</b></big>")
        grid.attach(title, 0, 0, 2, 1)

        subtitle = Gtk.Label(label="Choose a capture mode or bind these commands to keyboard shortcuts.")
        subtitle.set_line_wrap(True)
        grid.attach(subtitle, 0, 1, 2, 1)

        # Buttons with descriptions
        buttons = [
            ("Capture Region", "Select an area of the screen", CaptureMode.REGION,
             "Shortcut: Print Screen → linuxshot region"),
            ("Capture Fullscreen", "Capture the entire screen", CaptureMode.FULLSCREEN,
             "Shortcut: Ctrl+Print Screen → linuxshot fullscreen"),
            ("Capture Window", "Capture the active window", CaptureMode.WINDOW,
             "Shortcut: Alt+Print Screen → linuxshot window"),
        ]

        for i, (label, desc, mode, shortcut_hint) in enumerate(buttons):
            btn = Gtk.Button()
            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            btn_label = Gtk.Label()
            btn_label.set_markup(f"<b>{label}</b>")
            btn_desc = Gtk.Label(label=desc)
            btn_desc.set_opacity(0.7)
            btn_box.pack_start(btn_label, False, False, 0)
            btn_box.pack_start(btn_desc, False, False, 0)
            btn.add(btn_box)
            btn.set_size_request(280, 70)
            btn.connect("clicked", self._on_capture_clicked, mode)
            grid.attach(btn, 0, i + 2, 1, 1)

            hint = Gtk.Label()
            hint.set_markup(f"<small><tt>{shortcut_hint}</tt></small>")
            hint.set_halign(Gtk.Align.START)
            grid.attach(hint, 1, i + 2, 1, 1)

        # Upload last button
        upload_btn = Gtk.Button(label="Upload Last Capture")
        upload_btn.set_size_request(280, 40)
        upload_btn.connect("clicked", self._on_upload_last)
        grid.attach(upload_btn, 0, len(buttons) + 2, 1, 1)

        # Open folder button
        folder_btn = Gtk.Button(label="Open Screenshots Folder")
        folder_btn.set_size_request(280, 40)
        folder_btn.connect("clicked", self._on_open_folder)
        grid.attach(folder_btn, 0, len(buttons) + 3, 1, 1)

        return grid

    # ── Tab: History ───────────────────────────────────────────────

    def _build_history_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self._on_refresh_history)
        toolbar.pack_start(refresh_btn, False, False, 0)

        clear_btn = Gtk.Button(label="Clear History")
        clear_btn.connect("clicked", self._on_clear_history)
        toolbar.pack_end(clear_btn, False, False, 0)
        vbox.pack_start(toolbar, False, False, 0)

        # List store: timestamp, filepath, mode, size, uploaded, url
        self.history_store = Gtk.ListStore(str, str, str, str, str, str)
        self._populate_history()

        # TreeView
        tree = Gtk.TreeView(model=self.history_store)
        tree.set_headers_visible(True)

        columns = [
            ("Time", 0, 150),
            ("File", 1, 250),
            ("Mode", 2, 80),
            ("Size", 3, 70),
            ("Uploaded", 4, 70),
        ]
        for title, idx, width in columns:
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
            col = Gtk.TreeViewColumn(title, renderer, text=idx)
            col.set_min_width(width)
            col.set_resizable(True)
            tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(tree)
        vbox.pack_start(scroll, True, True, 0)

        self.history_tree = tree
        return vbox

    def _populate_history(self) -> None:
        self.history_store.clear()
        self.history.load()
        for entry in self.history.get_entries(limit=100):
            size_str = f"{entry.filesize / 1024:.0f} KB" if entry.filesize else "?"
            uploaded_str = "Yes" if entry.uploaded else "No"
            self.history_store.append([
                entry.timestamp[:19],
                os.path.basename(entry.filepath),
                entry.mode,
                size_str,
                uploaded_str,
                entry.upload_url,
            ])

    # ── Tab: Settings ──────────────────────────────────────────────

    def _build_settings_tab(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(16)
        grid.set_margin_top(16)
        grid.set_margin_bottom(16)
        grid.set_margin_start(16)
        grid.set_margin_end(16)

        row = 0

        # Section: General
        row = self._add_section_header(grid, "General", row)
        row = self._add_toggle(grid, "Copy image to clipboard", "copy_image_to_clipboard", row)
        row = self._add_toggle(grid, "Show notification after capture", "show_notification", row)
        row = self._add_toggle(grid, "Save screenshots to disk", "save_to_disk", row)
        row = self._add_toggle(grid, "Save capture history", "save_history", row)

        # Section: Upload
        row = self._add_section_header(grid, "Upload", row)
        row = self._add_toggle(grid, "Auto-upload after capture", "auto_upload", row)
        row = self._add_toggle(grid, "Copy URL to clipboard after upload", "copy_url_to_clipboard", row)
        row = self._add_entry(grid, "Imgur Client ID", "imgur_client_id", row)

        # Imgur account row
        row = self._add_imgur_account_row(grid, row)

        # Section: Capture
        row = self._add_section_header(grid, "Capture", row)
        row = self._add_spin(grid, "Capture delay (seconds)", "capture_delay", 0, 30, row)

        # Section: Image
        row = self._add_section_header(grid, "Image", row)
        row = self._add_combo(grid, "Image format", "image_format", ["png", "jpg", "webp"], row)
        row = self._add_spin(grid, "JPEG quality", "jpg_quality", 1, 100, row)

        # Section: Paths
        row = self._add_section_header(grid, "Paths", row)
        path_label = Gtk.Label(label="Config file:")
        path_label.set_halign(Gtk.Align.START)
        grid.attach(path_label, 0, row, 1, 1)
        path_value = Gtk.Label(label=self.config.path)
        path_value.set_halign(Gtk.Align.START)
        path_value.set_selectable(True)
        grid.attach(path_value, 1, row, 1, 1)
        row += 1

        dir_label = Gtk.Label(label="Screenshots dir:")
        dir_label.set_halign(Gtk.Align.START)
        grid.attach(dir_label, 0, row, 1, 1)
        dir_value = Gtk.Label(label=self.config.get_screenshot_dir())
        dir_value.set_halign(Gtk.Align.START)
        dir_value.set_selectable(True)
        grid.attach(dir_value, 1, row, 1, 1)
        row += 1

        # Save button
        save_btn = Gtk.Button(label="Save Settings")
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self._on_save_settings)
        grid.attach(save_btn, 0, row, 2, 1)

        scroll.add(grid)
        return scroll

    # ── Settings helpers ───────────────────────────────────────────

    def _add_section_header(self, grid: Gtk.Grid, title: str, row: int) -> int:
        label = Gtk.Label()
        label.set_markup(f"\n<b>{title}</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        return row + 1

    def _add_toggle(self, grid: Gtk.Grid, label: str, key: str, row: int) -> int:
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        switch = Gtk.Switch()
        switch.set_active(bool(self.config[key]))
        switch.set_halign(Gtk.Align.END)
        switch.connect("state-set", self._on_switch_changed, key)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(switch, 1, row, 1, 1)
        return row + 1

    def _add_entry(self, grid: Gtk.Grid, label: str, key: str, row: int) -> int:
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        entry = Gtk.Entry()
        entry.set_text(str(self.config[key]))
        entry.connect("changed", self._on_entry_changed, key)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(entry, 1, row, 1, 1)
        return row + 1

    def _add_spin(self, grid: Gtk.Grid, label: str, key: str, min_val: int, max_val: int, row: int) -> int:
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        adj = Gtk.Adjustment(value=self.config[key], lower=min_val, upper=max_val, step_increment=1)
        spin = Gtk.SpinButton(adjustment=adj)
        spin.set_numeric(True)
        spin.connect("value-changed", self._on_spin_changed, key)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(spin, 1, row, 1, 1)
        return row + 1

    def _add_combo(self, grid: Gtk.Grid, label: str, key: str, options: list, row: int) -> int:
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        combo = Gtk.ComboBoxText()
        for opt in options:
            combo.append_text(opt)
        current = self.config[key]
        if current in options:
            combo.set_active(options.index(current))
        combo.connect("changed", self._on_combo_changed, key)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(combo, 1, row, 1, 1)
        return row + 1

    def _add_imgur_account_row(self, grid: Gtk.Grid, row: int) -> int:
        """Add Imgur login/logout button + status label."""
        from ..imgur_auth import ImgurAuth

        lbl = Gtk.Label(label="Imgur Account")
        lbl.set_halign(Gtk.Align.START)
        grid.attach(lbl, 0, row, 1, 1)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self._imgur_auth = ImgurAuth()
        self._imgur_status_label = Gtk.Label()
        self._imgur_login_btn = Gtk.Button()
        self._update_imgur_status()

        hbox.pack_start(self._imgur_status_label, False, False, 0)
        hbox.pack_end(self._imgur_login_btn, False, False, 0)
        grid.attach(hbox, 1, row, 1, 1)
        return row + 1

    def _update_imgur_status(self) -> None:
        """Refresh the Imgur login status label and button."""
        if self._imgur_auth.is_logged_in:
            self._imgur_status_label.set_text(f"Signed in as: {self._imgur_auth.username}")
            self._imgur_login_btn.set_label("Sign Out")
            try:
                self._imgur_login_btn.disconnect_by_func(self._on_imgur_login)
            except TypeError:
                pass
            self._imgur_login_btn.connect("clicked", self._on_imgur_logout)
        else:
            self._imgur_status_label.set_text("Not signed in (anonymous uploads)")
            self._imgur_login_btn.set_label("Sign In to Imgur")
            try:
                self._imgur_login_btn.disconnect_by_func(self._on_imgur_logout)
            except TypeError:
                pass
            self._imgur_login_btn.connect("clicked", self._on_imgur_login)

    def _on_imgur_login(self, btn) -> None:
        """Open Imgur auth flow in a dialog."""
        from ..imgur_auth import ImgurAuth

        config = Config.get()
        client_id = config["imgur_client_id"]
        url = f"https://api.imgur.com/oauth2/authorize?client_id={client_id}&response_type=pin"

        import webbrowser
        webbrowser.open(url)

        # Show a dialog to enter the PIN
        dialog = Gtk.Dialog(
            title="Imgur Sign In",
            transient_for=self,
            flags=0,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Sign In", Gtk.ResponseType.OK)
        dialog.set_default_size(400, -1)

        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        info = Gtk.Label()
        info.set_markup(
            "A browser window has opened to Imgur.\n"
            "Authorize LinuxShot, then paste the <b>PIN</b> below:"
        )
        info.set_line_wrap(True)
        content.add(info)

        pin_entry = Gtk.Entry()
        pin_entry.set_placeholder_text("Enter PIN from Imgur")
        pin_entry.set_activates_default(True)
        content.add(pin_entry)

        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()

        response = dialog.run()
        pin = pin_entry.get_text().strip()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not pin:
            return

        auth = ImgurAuth()
        if auth._exchange_pin(pin):
            self._imgur_auth = auth
            self._update_imgur_status()
            msg = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text=f"Signed in as {auth.username}!",
            )
            msg.run()
            msg.destroy()
        else:
            msg = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Sign in failed. Check the PIN and try again.",
            )
            msg.run()
            msg.destroy()

    def _on_imgur_logout(self, btn) -> None:
        self._imgur_auth.logout()
        self._update_imgur_status()

    # ── Signal handlers ────────────────────────────────────────────

    def _on_capture_clicked(self, btn, mode: CaptureMode) -> None:
        self.hide()
        # Small delay to let the window hide before capture
        GLib.timeout_add(200, self._do_capture_and_show, mode)

    def _do_capture_and_show(self, mode: CaptureMode) -> bool:
        def capture():
            self.app.run_capture(mode)
            GLib.idle_add(self._populate_history)
            GLib.idle_add(self.present)  # re-show window after capture
        threading.Thread(target=capture, daemon=True).start()
        return False  # Don't repeat

    def _on_upload_last(self, btn) -> None:
        def do_upload():
            self.app.upload_last()
            GLib.idle_add(self._populate_history)
        threading.Thread(target=do_upload, daemon=True).start()

    def _on_open_folder(self, btn) -> None:
        self.app.open_screenshots_dir()

    def _on_refresh_history(self, btn) -> None:
        self._populate_history()

    def _on_clear_history(self, btn) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Clear all history?",
        )
        dialog.format_secondary_text("This cannot be undone.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self.history.clear()
            self._populate_history()

    def _on_switch_changed(self, switch, state, key) -> None:
        self.config[key] = state

    def _on_entry_changed(self, entry, key) -> None:
        self.config[key] = entry.get_text()

    def _on_spin_changed(self, spin, key) -> None:
        self.config[key] = int(spin.get_value())

    def _on_combo_changed(self, combo, key) -> None:
        text = combo.get_active_text()
        if text:
            self.config[key] = text

    def _on_save_settings(self, btn) -> None:
        self.config.save()
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Settings saved!",
        )
        dialog.run()
        dialog.destroy()


class HistoryDialog(Gtk.Dialog):
    """Standalone history dialog, used from the tray."""

    def __init__(self):
        super().__init__(title="LinuxShot - History", flags=0)
        self.set_default_size(600, 400)
        self.add_button("Close", Gtk.ResponseType.CLOSE)

        history = History()
        entries = history.get_entries(limit=50)

        store = Gtk.ListStore(str, str, str, str)
        for entry in entries:
            size_str = f"{entry.filesize / 1024:.0f} KB" if entry.filesize else "?"
            uploaded = entry.upload_url if entry.uploaded else "-"
            store.append([entry.timestamp[:19], os.path.basename(entry.filepath), size_str, uploaded])

        tree = Gtk.TreeView(model=store)
        for i, (title, width) in enumerate([("Time", 150), ("File", 200), ("Size", 70), ("URL", 200)]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_min_width(width)
            col.set_resizable(True)
            tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.add(tree)
        self.get_content_area().pack_start(scroll, True, True, 0)
        self.show_all()


def run_gui() -> None:
    """Entry point for the GUI."""
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
