#!/usr/bin/env python3
"""Native GTK4 clipboard panel for Omarchy."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import threading
import time
import tomllib
import uuid
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk


BASE = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "omarchy-clipboard"
STATE = BASE / "history.json"
SOCKET = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omarchy-clipboard.sock"


def theme() -> dict[str, str]:
    values = {
        "background": "#0c0b0c", "panel": "#242126", "selection": "#584e51",
        "foreground": "#fafcfb", "muted": "#aaa3a8", "accent": "#b59790",
        "cyan": "#a5a0b6", "green": "#87a9b0", "yellow": "#ebcb8b",
    }
    try:
        colors = tomllib.loads((Path.home() / ".local/state/omarchy/current/theme/colors.toml").read_text())
        values.update({key: colors.get(key, value) for key, value in values.items()})
        if values["panel"].lower() == values["background"].lower():
            values["panel"] = values["selection"]
    except (OSError, tomllib.TOMLDecodeError):
        pass
    return values


COLORS = theme()


def clip(*args: str) -> bytes | None:
    try:
        return subprocess.run(["wl-paste", "--no-newline", *args], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=2, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


class ClipboardApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.omarchy.Clipboard",
                         flags=Gio.ApplicationFlags.NON_UNIQUE if False else 0)
        BASE.mkdir(parents=True, exist_ok=True)
        self.boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        self.history = self.load()
        self.last_signature: str | None = None
        self.window: Gtk.ApplicationWindow | None = None
        self.items_box: Gtk.ListBox | None = None
        self.scroller: Gtk.ScrolledWindow | None = None
        self.cards: list[Gtk.Box] = []
        self.rows: list[Gtk.ListBoxRow] = []
        self.selected = 0
        self.notice = ""
        self.holder: subprocess.Popen[bytes] | None = None
        self.server: socket.socket | None = None
        self.previous_window_address: str | None = None
        self.scroll_animation_id: int | None = None

    def load(self) -> list[dict]:
        try:
            state = json.loads(STATE.read_text())
            items = state if isinstance(state, list) else state.get("items", [])
            return items if isinstance(state, list) or state.get("boot_id") == self.boot_id else [x for x in items if x.get("pinned")]
        except (OSError, ValueError, TypeError):
            return []

    def save(self) -> None:
        try:
            tmp = STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"boot_id": self.boot_id, "items": self.history}, ensure_ascii=False))
            tmp.replace(STATE)
        except OSError:
            pass

    def do_activate(self) -> None:
        self.hold()
        self.install_css()
        self.poll()
        self.start_socket()

    def install_css(self) -> None:
        css = f"""
        window {{ background: {COLORS['background']}; }}
        .panel {{ background: {COLORS['background']}; padding: 8px; }}
        .footer {{ color: {COLORS['muted']}; font-size: 12px; }}
        .card {{ background: transparent; border: 0; border-bottom: 1px solid {COLORS['muted']}; border-radius: 0; padding: 9px 12px; }}
        .card.active {{ background: {COLORS['selection']}; border: 1px solid {COLORS['accent']}; border-radius: 0; }}
        .card.pinned {{ border-left: 2px solid {COLORS['yellow']}; }}
        list row, list row:selected, list row:focus, list row:focus-visible {{
            background: transparent; border: 0; outline: none; box-shadow: none;
        }}
        .item-text {{ color: {COLORS['foreground']}; font-size: 15px; }}
        .kind {{ color: {COLORS['cyan']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
        .pin {{ color: {COLORS['yellow']}; font-size: 16px; }}
        .pin-badge {{ color: {COLORS['yellow']}; font-size: 10px; font-weight: 800; letter-spacing: 0.8px; }}
        button {{ background: transparent; border: 0; }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def start_socket(self) -> None:
        try:
            SOCKET.unlink(missing_ok=True)
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server.bind(str(SOCKET))
            self.server.listen(4)
            threading.Thread(target=self.socket_loop, daemon=True).start()
        except OSError:
            pass

    def socket_loop(self) -> None:
        assert self.server
        while True:
            try:
                conn, _ = self.server.accept()
                conn.close()
                GLib.idle_add(self.show_panel)
            except OSError:
                return

    def poll(self) -> bool:
        types = clip("--list-types")
        if types:
            names = types.decode(errors="ignore").splitlines()
            image_type = next((x for x in names if x.startswith("image/")), None)
            if image_type:
                data = clip("--type", image_type)
                if data:
                    self.add_image(data, image_type)
            else:
                data = clip()
                if data:
                    self.add_text(data.decode(errors="replace"))
        GLib.timeout_add(350, self.poll)
        return False

    def add_text(self, text: str) -> None:
        text = text.strip("\x00")
        if not text or f"text:{text}" == self.last_signature:
            return
        self.last_signature = f"text:{text}"
        old = next((x for x in self.history if x.get("kind") == "text" and x.get("text") == text), None)
        self.history = [x for x in self.history if not (x.get("kind") == "text" and x.get("text") == text)]
        self.history.insert(0, {"id": uuid.uuid4().hex, "kind": "text", "text": text, "time": time.time(), "pinned": bool(old and old.get("pinned"))})
        self.save()

    def add_image(self, data: bytes, mime: str) -> None:
        signature = f"image:{len(data)}:{hash(data[:4096])}"
        if signature == self.last_signature:
            return
        self.last_signature = signature
        path = BASE / f"{uuid.uuid4().hex}.{mime.rsplit('/', 1)[-1].replace('jpeg', 'jpg')}"
        path.write_bytes(data)
        old = next((x for x in self.history if x.get("signature") == signature), None)
        self.history = [x for x in self.history if x.get("signature") != signature]
        self.history.insert(0, {"id": uuid.uuid4().hex, "kind": "image", "path": str(path), "mime": mime, "signature": signature, "time": time.time(), "pinned": bool(old and old.get("pinned"))})
        self.save()

    def filtered(self) -> list[dict]:
        return self.history

    def show_panel(self) -> bool:
        self.selected = 0
        self.previous_window_address = self.active_window_address()
        if self.window:
            self.window.set_visible(True)
            self.render_items()
            self.window.present()
            return False
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Omarchy Clipboard")
        self.window.set_default_size(360, 330)
        self.window.set_size_request(360, 330)
        self.window.set_resizable(False)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.add_css_class("panel")
        self.items_box = Gtk.ListBox()
        self.items_box.add_css_class("items")
        self.items_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.items_box.set_focusable(False)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_vexpand(True)
        self.scroller.set_focusable(False)
        self.scroller.set_child(self.items_box)
        panel.append(self.scroller)
        footer = Gtk.Label(label=self.notice or "↑ ↓ navigate    Enter select    P pin    Delete remove    Esc close", xalign=0)
        footer.add_css_class("footer")
        footer.set_margin_top(8)
        panel.append(footer)
        self.window.set_child(panel)
        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self.key_pressed)
        self.window.add_controller(key)
        self.render_items()
        self.window.present()
        self.window.grab_focus()
        return False

    @staticmethod
    def active_window_address() -> str | None:
        try:
            data = json.loads(subprocess.check_output(
                ["/usr/bin/hyprctl", "activewindow", "-j"], stderr=subprocess.DEVNULL
            ))
            return data.get("address")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None

    def render_items(self) -> None:
        if not self.items_box:
            return
        self.cards = []
        self.rows = []
        while (row := self.items_box.get_row_at_index(0)):
            self.items_box.remove(row)
        for index, item in enumerate(self.filtered()[:8]):
            row = Gtk.ListBoxRow()
            row.set_margin_bottom(0)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class("card")
            if index == self.selected:
                box.add_css_class("active")
            if item.get("pinned"):
                box.add_css_class("pinned")
            if item["kind"] == "image":
                picture = Gtk.Picture.new_for_filename(item["path"])
                picture.set_size_request(72, 46)
                picture.set_content_fit(Gtk.ContentFit.COVER)
                box.append(picture)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            body.set_hexpand(True)
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            if item.get("pinned"):
                pin = Gtk.Label(label="● PINNED")
                pin.add_css_class("pin-badge")
                line.append(pin)
            text = item.get("text", "Image").replace("\n", " ↵ ")
            label = Gtk.Label(label=text[:180] + ("…" if len(text) > 180 else ""), xalign=0)
            label.set_wrap(True)
            label.set_wrap_mode(2)
            label.add_css_class("item-text")
            line.append(label)
            body.append(line)
            kind = Gtk.Label(label="IMAGE" if item["kind"] == "image" else "TEXT", xalign=0)
            kind.add_css_class("kind")
            body.append(kind)
            box.append(body)
            pin_button = Gtk.Button(label="★" if item.get("pinned") else "☆")
            pin_button.set_tooltip_text("Unpin item" if item.get("pinned") else "Pin item")
            pin_button.add_css_class("pin")
            pin_button.connect("clicked", lambda _b, i=index: self.pin_index(i))
            box.append(pin_button)
            row.set_child(box)
            click = Gtk.GestureClick()
            click.connect("released", lambda _gesture, _count, _x, _y, i=index: self.activate_index(i))
            row.add_controller(click)
            self.items_box.append(row)
            self.cards.append(box)
            self.rows.append(row)

    def key_pressed(self, _controller, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval)
        items = self.filtered()
        if name == "Escape":
            self.window.set_visible(False)
        elif name in ("Return", "KP_Enter") and items:
            self.activate_index(self.selected)
        elif name == "Down" and items:
            self.selected = min(self.selected + 1, min(len(items), 8) - 1)
            self.select_current_row()
        elif name == "Up" and items:
            self.selected = max(0, self.selected - 1)
            self.select_current_row()
        elif name in ("p", "P") and items:
            self.pin_index(self.selected)
        elif name in ("Delete", "KP_Delete") and items:
            self.delete_index(self.selected)
        else:
            return False
        return True

    def select_current_row(self) -> None:
        """Move the active-card style without rebuilding the panel."""
        for index, card in enumerate(self.cards):
            if index == self.selected:
                card.add_css_class("active")
            else:
                card.remove_css_class("active")
            card.queue_draw()
        GLib.idle_add(self.center_current_row)

    def center_current_row(self) -> bool:
        """Smoothly keep keyboard navigation centered in the scroll viewport."""
        if not self.scroller or not (0 <= self.selected < len(self.rows)):
            return False
        adjustment = self.scroller.get_vadjustment()
        row = self.rows[self.selected]
        allocation = row.get_allocation()
        target = allocation.y + allocation.height / 2 - adjustment.get_page_size() / 2
        maximum = max(adjustment.get_lower(), adjustment.get_upper() - adjustment.get_page_size())
        target = max(adjustment.get_lower(), min(target, maximum))
        self.animate_scroll(adjustment, target)
        return False

    def animate_scroll(self, adjustment: Gtk.Adjustment, target: float) -> None:
        if self.scroll_animation_id is not None:
            GLib.source_remove(self.scroll_animation_id)
        start = adjustment.get_value()
        started_at = time.monotonic()
        duration = 0.12

        def step() -> bool:
            progress = min((time.monotonic() - started_at) / duration, 1.0)
            eased = 1 - (1 - progress) ** 3
            adjustment.set_value(start + (target - start) * eased)
            if progress >= 1:
                self.scroll_animation_id = None
                return False
            return True

        self.scroll_animation_id = GLib.timeout_add(16, step)

    def pin_index(self, index: int) -> None:
        items = self.filtered()
        if index < len(items):
            items[index]["pinned"] = not items[index].get("pinned", False)
            self.notice = "Pinned — saved across restarts" if items[index]["pinned"] else "Unpinned — available this session"
            self.save()
            self.render_items()
            GLib.timeout_add(1400, self.clear_notice)

    def delete_index(self, index: int) -> None:
        items = self.filtered()
        if index >= len(items):
            return
        item = items[index]
        if item.get("pinned"):
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                text="Delete pinned clipboard item?",
                secondary_text="This pinned item will be removed permanently.",
            )
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Delete", Gtk.ResponseType.ACCEPT)
            dialog.connect("response", lambda box, response, target=item: self.confirm_delete(box, response, target))
            dialog.present()
            return
        self.remove_item(item)

    def confirm_delete(self, dialog: Gtk.MessageDialog, response: int, item: dict) -> None:
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            self.remove_item(item)

    def remove_item(self, item: dict) -> None:
        self.history.remove(item)
        if item.get("kind") == "image":
            try:
                Path(item["path"]).unlink(missing_ok=True)
            except OSError:
                pass
        self.selected = max(0, min(self.selected, len(self.filtered()) - 1))
        self.save()
        self.render_items()

    def clear_notice(self) -> bool:
        self.notice = ""
        return False

    def activate_index(self, index: int) -> None:
        items = self.filtered()
        if index >= len(items):
            return
        item = items[index]
        if item["kind"] == "image":
            self.replace_clipboard(Path(item["path"]).read_bytes(), item.get("mime", "image/png"))
        else:
            self.replace_clipboard(item["text"].encode(), "text/plain;charset=utf-8")
        self.last_signature = None
        self.window.set_visible(False)
        if item["kind"] == "text":
            GLib.timeout_add(120, lambda: self.restore_focus_and_type(item["text"]))

    def restore_focus_and_type(self, text: str) -> bool:
        if self.previous_window_address:
            subprocess.run(
                [
                    "/usr/bin/hyprctl",
                    "eval",
                    f"hl.dispatch(hl.dsp.focus({{ window = 'address:{self.previous_window_address}' }}))",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        # Give Hyprland one frame to focus the former text field before
        # entering the selected text. The clipboard remains owned separately.
        GLib.timeout_add(160, lambda: self.type_selected_text(text))
        return False

    @staticmethod
    def type_selected_text(text: str) -> bool:
        subprocess.run(["wtype", "--", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return False

    def replace_clipboard(self, data: bytes, mime: str | None = None) -> None:
        if self.holder and self.holder.poll() is None:
            self.holder.terminate()
        command = ["wl-copy", "--foreground"] + (["--type", mime] if mime else [])
        try:
            self.holder = subprocess.Popen(command, stdin=subprocess.PIPE)
            self.holder.stdin.write(data)
            self.holder.stdin.close()
        except (OSError, BrokenPipeError):
            self.holder = None


def toggle() -> int:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.connect(str(SOCKET))
        return 0
    except OSError:
        return 1


if __name__ == "__main__":
    if "--toggle" in os.sys.argv:
        raise SystemExit(toggle())
    app = ClipboardApp()
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    app.run()
