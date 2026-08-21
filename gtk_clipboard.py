#!/usr/bin/env python3
"""Native GTK4 clipboard panel for Omarchy."""

from __future__ import annotations

import json
import os
import shutil
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
        self.search: Gtk.Entry | None = None
        self.selected = 0
        self.query = ""
        self.notice = ""
        self.holder: subprocess.Popen[bytes] | None = None
        self.server: socket.socket | None = None

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
        .panel {{ background: {COLORS['background']}; padding: 28px; }}
        .title {{ color: {COLORS['foreground']}; font-size: 30px; font-weight: 800; }}
        .subtitle, .footer {{ color: {COLORS['muted']}; font-size: 12px; }}
        .search {{ background: {COLORS['panel']}; color: {COLORS['foreground']}; border: 1px solid {COLORS['selection']}; border-radius: 10px; padding: 13px 16px; font-size: 16px; }}
        .card {{ background: {COLORS['panel']}; border: 1px solid {COLORS['selection']}; border-radius: 9px; padding: 14px; }}
        .card:selected {{ background: {COLORS['selection']}; border-color: {COLORS['accent']}; }}
        .card.pinned {{ border-color: {COLORS['yellow']}; }}
        .item-text {{ color: {COLORS['foreground']}; font-size: 17px; }}
        .kind {{ color: {COLORS['cyan']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
        .pin {{ color: {COLORS['yellow']}; font-size: 17px; }}
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
        q = self.query.lower().strip()
        return [x for x in self.history if not q or (x.get("kind") == "text" and q in x.get("text", "").lower())]

    def show_panel(self) -> bool:
        self.selected = 0
        self.query = ""
        if self.window:
            self.window.set_visible(True)
            self.render_items()
            self.window.present()
            if self.search:
                self.search.grab_focus()
            return False
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Omarchy Clipboard")
        self.window.set_default_size(700, 760)
        self.window.set_resizable(False)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.add_css_class("panel")
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Label(label="▣")
        icon.set_css_classes(["title"])
        head.append(icon)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Clipboard", xalign=0)
        title.add_css_class("title")
        titles.append(title)
        subtitle = Gtk.Label(label="Everything you copy, ready when you need it", xalign=0)
        subtitle.add_css_class("subtitle")
        titles.append(subtitle)
        head.append(titles)
        panel.append(head)
        self.search = Gtk.Entry(placeholder_text="Search your clipboard")
        self.search.add_css_class("search")
        self.search.set_margin_top(20)
        self.search.set_margin_bottom(16)
        self.search.connect("changed", self.search_changed)
        panel.append(self.search)
        self.items_box = Gtk.ListBox()
        self.items_box.add_css_class("items")
        self.items_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.items_box.connect("row-activated", lambda _box, row: self.activate_index(row.get_index()))
        panel.append(self.items_box)
        footer = Gtk.Label(label=self.notice or "↑ ↓ navigate    Enter select    P pin    Esc close", xalign=0)
        footer.add_css_class("footer")
        footer.set_margin_top(14)
        panel.append(footer)
        self.window.set_child(panel)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self.key_pressed)
        self.window.add_controller(key)
        self.render_items()
        self.window.present()
        self.search.grab_focus()
        return False

    def search_changed(self, entry: Gtk.Entry) -> None:
        self.query = entry.get_text()
        self.selected = 0
        self.render_items()

    def render_items(self) -> None:
        if not self.items_box:
            return
        while (row := self.items_box.get_row_at_index(0)):
            self.items_box.remove(row)
        for index, item in enumerate(self.filtered()[:8]):
            row = Gtk.ListBoxRow()
            row.set_margin_bottom(7)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class("card")
            if item.get("pinned"):
                box.add_css_class("pinned")
            if item["kind"] == "image":
                picture = Gtk.Picture.new_for_filename(item["path"])
                picture.set_size_request(92, 60)
                picture.set_content_fit(Gtk.ContentFit.COVER)
                box.append(picture)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            body.set_hexpand(True)
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            if item.get("pinned"):
                pin = Gtk.Label(label="⚑")
                pin.add_css_class("pin")
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
            pin_button.add_css_class("pin")
            pin_button.connect("clicked", lambda _b, i=index: self.pin_index(i))
            box.append(pin_button)
            row.set_child(box)
            self.items_box.append(row)
        if self.items_box.get_row_at_index(self.selected):
            self.items_box.select_row(self.items_box.get_row_at_index(self.selected))

    def key_pressed(self, _controller, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval)
        items = self.filtered()
        if name == "Escape":
            self.window.set_visible(False)
        elif name in ("Return", "KP_Enter") and items:
            self.activate_index(self.selected)
        elif name == "Down" and items:
            self.selected = min(self.selected + 1, min(len(items), 8) - 1)
            self.render_items()
        elif name == "Up" and items:
            self.selected = max(0, self.selected - 1)
            self.render_items()
        elif name in ("p", "P") and items:
            self.pin_index(self.selected)
        else:
            return False
        return True

    def pin_index(self, index: int) -> None:
        items = self.filtered()
        if index < len(items):
            items[index]["pinned"] = not items[index].get("pinned", False)
            self.notice = "Pinned — saved across restarts" if items[index]["pinned"] else "Unpinned — available this session"
            self.save()
            self.render_items()
            GLib.timeout_add(1400, self.clear_notice)

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
            self.replace_clipboard(item["text"].encode())
            if shutil.which("wtype"):
                GLib.timeout_add(100, lambda: (subprocess.run(["wtype", "--", item["text"]], check=False), False)[1])
        self.last_signature = None
        self.window.set_visible(False)

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
