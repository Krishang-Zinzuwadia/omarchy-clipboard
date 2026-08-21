#!/usr/bin/env python3
"""Windows+V-style clipboard history for Omarchy/Hyprland."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import uuid
from pathlib import Path
import tomllib
import tkinter as tk
from tkinter import font as tkfont


APP_NAME = "Omarchy Clipboard"
BASE_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "omarchy-clipboard"
HISTORY_FILE = BASE_DIR / "history.json"
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omarchy-clipboard.sock"
POLL_SECONDS = 0.35

# Omarchy Nord palette (kept in sync with /usr/share/omarchy/themes/nord/colors.toml).
BG = "#222730"
PANEL = "#2e3440"
PANEL_HOVER = "#3b4252"
TEXT = "#d8dee9"
MUTED = "#667080"
ACCENT = "#81a1c1"
ACCENT_DARK = "#434c5e"
DIVIDER = "#4c566a"
CYAN = "#88c0d0"
GREEN = "#a3be8c"
YELLOW = "#ebcb8b"


def load_omarchy_theme() -> None:
    """Use the active Omarchy theme, falling back to Nord defaults."""
    global BG, PANEL, TEXT, MUTED, ACCENT, ACCENT_DARK, DIVIDER, CYAN, GREEN, YELLOW
    theme_file = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
    try:
        colors = tomllib.loads(theme_file.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return
    BG = colors.get("background", BG)
    PANEL = colors.get("lighter_background", PANEL)
    TEXT = colors.get("foreground", TEXT)
    MUTED = colors.get("dark_foreground", MUTED)
    ACCENT = colors.get("accent", ACCENT)
    ACCENT_DARK = colors.get("selection", ACCENT_DARK)
    DIVIDER = colors.get("muted", DIVIDER)
    CYAN = colors.get("cyan", CYAN)
    GREEN = colors.get("green", GREEN)
    YELLOW = colors.get("yellow", YELLOW)


load_omarchy_theme()


def run_clipboard(*args: str, input_data: bytes | None = None) -> bytes | None:
    try:
        return subprocess.run(
            ["wl-paste", "--no-newline", *args],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None


class ClipboardApp:
    def __init__(self) -> None:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        self.boot_id = self.current_boot_id()
        self.history: list[dict] = self.load_history()
        self.last_signature: str | None = None
        self.visible = False
        self.selected = 0
        self.query = ""
        self.pin_notice = ""
        self.server: socket.socket | None = None
        self.image_refs: list[tk.PhotoImage] = []

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        families = set(tkfont.families(self.root))
        self.ui_font = "Inter" if "Inter" in families else "Liberation Sans"
        self.mono_font = "JetBrains Mono" if "JetBrains Mono" in families else "monospace"
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.bind("<Escape>", lambda _e: self.hide())
        self.root.bind("<Return>", lambda _e: self.activate())
        self.root.bind("<KP_Enter>", lambda _e: self.activate())
        self.root.bind("<Up>", lambda _e: self.move(-1))
        self.root.bind("<Down>", lambda _e: self.move(1))
        self.root.bind("<Control-v>", lambda _e: self.activate())
        self.root.bind("<KeyRelease>", self.on_key)

        self.poll_clipboard()
        self.start_socket()

    @staticmethod
    def current_boot_id() -> str:
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except OSError:
            return "unknown"

    def load_history(self) -> list[dict]:
        try:
            state = json.loads(HISTORY_FILE.read_text())
            if isinstance(state, list):
                return [item for item in state if item.get("pinned")]
            if state.get("boot_id") == self.boot_id:
                return state.get("items", [])
            return [item for item in state.get("items", []) if item.get("pinned")]
        except (OSError, ValueError, TypeError):
            return []

    def save_history(self) -> None:
        tmp = HISTORY_FILE.with_suffix(".tmp")
        try:
            state = {"boot_id": self.boot_id, "items": self.history}
            tmp.write_text(json.dumps(state, ensure_ascii=False))
            tmp.replace(HISTORY_FILE)
        except OSError:
            pass

    def start_socket(self) -> None:
        try:
            SOCKET_PATH.unlink(missing_ok=True)
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server.bind(str(SOCKET_PATH))
            self.server.listen(4)
            self.server.setblocking(False)
            self.root.after(100, self.accept_socket)
        except OSError:
            self.server = None

    def accept_socket(self) -> None:
        if self.server:
            try:
                conn, _ = self.server.accept()
                conn.close()
                self.show()
            except BlockingIOError:
                pass
            except OSError:
                pass
        self.root.after(100, self.accept_socket)

    def poll_clipboard(self) -> None:
        types = run_clipboard("--list-types")
        if types:
            type_list = types.decode(errors="ignore").splitlines()
            image_type = next((t for t in type_list if t.startswith("image/")), None)
            if image_type:
                data = run_clipboard("--type", image_type)
                if data:
                    self.add_image(data, image_type)
            else:
                data = run_clipboard()
                if data:
                    self.add_text(data.decode(errors="replace"))
        self.root.after(int(POLL_SECONDS * 1000), self.poll_clipboard)

    def add_text(self, text: str) -> None:
        text = text.strip("\x00")
        if not text or len(text) > 1_000_000:
            return
        signature = f"text:{text}"
        if signature == self.last_signature:
            return
        self.last_signature = signature
        previous = next((x for x in self.history if x["kind"] == "text" and x["text"] == text), None)
        self.history = [x for x in self.history if not (x["kind"] == "text" and x["text"] == text)]
        self.history.insert(0, {"id": uuid.uuid4().hex, "kind": "text", "text": text, "time": time.time(), "pinned": bool(previous and previous.get("pinned"))})
        self.save_history()

    def add_image(self, data: bytes, mime: str) -> None:
        signature = f"image:{len(data)}:{hash(data[:4096])}"
        if signature == self.last_signature:
            return
        self.last_signature = signature
        ext = mime.split("/", 1)[-1].replace("jpeg", "jpg")
        path = BASE_DIR / f"{uuid.uuid4().hex}.{ext}"
        try:
            path.write_bytes(data)
        except OSError:
            return
        previous = next((x for x in self.history if x["kind"] == "image" and x.get("signature") == signature), None)
        self.history = [x for x in self.history if not (x["kind"] == "image" and x.get("signature") == signature)]
        self.history.insert(0, {"id": uuid.uuid4().hex, "kind": "image", "path": str(path), "mime": mime, "signature": signature, "time": time.time(), "pinned": bool(previous and previous.get("pinned"))})
        self.save_history()

    def filtered(self) -> list[dict]:
        needle = self.query.lower().strip()
        if not needle:
            return self.history
        return [x for x in self.history if x["kind"] == "text" and needle in x["text"].lower()]

    def show(self) -> None:
        self.visible = True
        self.selected = 0
        self.query = ""
        self.draw()
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def hide(self) -> None:
        self.visible = False
        self.root.withdraw()

    def move(self, amount: int) -> str:
        items = self.filtered()
        if items:
            self.selected = (self.selected + amount) % len(items)
            self.draw()
        return "break"

    def on_key(self, event: tk.Event) -> None:
        if not self.visible:
            return
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        if event.keysym.lower() == "p" and not (event.state & 0x4):
            self.toggle_pin()
            return
        if event.keysym == "BackSpace":
            self.query = self.query[:-1]
        elif len(event.char) == 1 and not (event.state & 0x4):
            self.query += event.char
        else:
            return
        self.selected = 0
        self.draw()

    def toggle_pin(self) -> str:
        items = self.filtered()
        if not items:
            return "break"
        item = items[self.selected]
        item["pinned"] = not item.get("pinned", False)
        self.pin_notice = "Pinned — saved across restarts" if item["pinned"] else "Unpinned — available this session"
        self.save_history()
        self.draw()
        self.root.after(1400, self.clear_pin_notice)
        return "break"

    def clear_pin_notice(self) -> None:
        if self.pin_notice:
            self.pin_notice = ""
            if self.visible:
                self.draw()

    def activate(self) -> str:
        items = self.filtered()
        if not items:
            return "break"
        item = items[self.selected]
        if item["kind"] == "image":
            data = Path(item["path"]).read_bytes()
            subprocess.run(["wl-copy", "--type", item.get("mime", "image/png")], input=data, check=False)
        else:
            subprocess.run(["wl-copy"], input=item["text"].encode(), check=False)
            # Once the panel closes, Hyprland restores the previously focused
            # window. Type into it as well as placing the value on the clipboard.
            self.root.after(90, lambda text=item["text"]: self.inject_text(text))
        self.last_signature = None
        self.hide()
        return "break"

    @staticmethod
    def inject_text(text: str) -> None:
        if shutil.which("wtype"):
            subprocess.run(["wtype", "--", text], check=False)

    def draw(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.image_refs.clear()
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        width = min(560, max(440, screen_w - 40))
        row_height = 76
        visible_limit = min(8, max(1, (screen_h - 290) // row_height))
        items = self.filtered()[:visible_limit]
        if items:
            self.selected = min(self.selected, len(items) - 1)
        height = max(300, 194 + len(items) * row_height)
        self.root.geometry(f"{width}x{height}+{(screen_w-width)//2}+{(screen_h-height)//2}")
        self.root.resizable(False, False)

        outer = tk.Frame(self.root, bg=BG, padx=28, pady=25)
        outer.pack(fill="both", expand=True)
        heading = tk.Frame(outer, bg=BG)
        heading.pack(fill="x", pady=(0, 18))
        tk.Label(heading, text="▣", bg=BG, fg=ACCENT, font=(self.ui_font, 25, "bold")).pack(side="left", padx=(0, 11))
        title = tk.Frame(heading, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="Clipboard", bg=BG, fg=TEXT, font=(self.ui_font, 22, "bold")).pack(anchor="w")
        tk.Label(title, text="Everything you copy, ready when you need it", bg=BG, fg=MUTED, font=(self.ui_font, 9)).pack(anchor="w", pady=(1, 0))
        tk.Label(heading, text="SUPER  V", bg=BG, fg=MUTED, font=(self.mono_font, 9, "bold")).pack(side="right", pady=(7, 0))

        search = tk.Frame(outer, bg=PANEL, height=46, highlightbackground=DIVIDER, highlightthickness=1)
        search.pack(fill="x", pady=(0, 15))
        search.pack_propagate(False)
        tk.Label(search, text="⌕", bg=PANEL, fg=ACCENT, font=(self.ui_font, 19)).pack(side="left", padx=(14, 8))
        tk.Label(search, text=self.query or "Search your clipboard", bg=PANEL, fg=TEXT if self.query else MUTED, font=(self.ui_font, 11), anchor="w").pack(side="left", fill="both", expand=True)
        tk.Label(search, text=f"{len(self.history)} saved", bg=PANEL, fg=MUTED, font=(self.ui_font, 9)).pack(side="right", padx=15)

        content = tk.Frame(outer, bg=BG)
        content.pack(fill="both", expand=True)
        if not items:
            empty = tk.Frame(content, bg=PANEL, highlightbackground=DIVIDER, highlightthickness=1, padx=20, pady=28)
            empty.pack(fill="x", pady=4)
            tk.Label(empty, text="Nothing here yet", bg=PANEL, fg=TEXT, font=(self.ui_font, 12, "bold")).pack()
            tk.Label(empty, text="Copy text or an image and it will appear here.", bg=PANEL, fg=MUTED, font=(self.ui_font, 10)).pack(pady=(7, 0))
        for index, item in enumerate(items):
            selected = index == self.selected
            card_bg = ACCENT_DARK if selected else PANEL
            card = tk.Frame(content, bg=card_bg, padx=15, pady=10, cursor="hand2",
                            highlightbackground=ACCENT if selected else DIVIDER,
                            highlightthickness=1)
            card.pack(fill="x", pady=(0, 7))
            card.bind("<Button-1>", lambda _e, i=index: self.select_and_activate(i))
            if item["kind"] == "image":
                try:
                    img = tk.PhotoImage(file=item["path"])
                    scale = max(1, (img.width() + 99) // 100, (img.height() + 51) // 52)
                    if scale > 1:
                        img = img.subsample(scale, scale)
                    self.image_refs.append(img)
                    thumb = tk.Frame(card, bg="#101214", width=82, height=52)
                    thumb.pack(side="left", padx=(0, 14))
                    thumb.pack_propagate(False)
                    tk.Label(thumb, image=img, bg="#101214").pack(expand=True)
                    label = "Image"
                except tk.TclError:
                    label = "Image (preview unavailable)"
            else:
                label = item["text"].replace("\n", " ↵ ")
                if len(label) > 110:
                    label = label[:107] + "…"
            text_box = tk.Frame(card, bg=card_bg)
            text_box.pack(side="left", fill="both", expand=True)
            tk.Label(text_box, text=label, bg=card_bg, fg=TEXT, font=(self.ui_font, 11), anchor="w", justify="left", wraplength=width - 180).pack(anchor="w", fill="x", expand=True)
            kind = "IMAGE" if item["kind"] == "image" else "TEXT"
            kind_color = GREEN if item["kind"] == "image" else CYAN
            tk.Label(text_box, text=kind, bg=card_bg, fg=kind_color, font=(self.mono_font, 8, "bold"), anchor="w").pack(anchor="w", pady=(4, 0))
            pin = tk.Button(card, text="★" if item.get("pinned") else "☆",
                            command=lambda i=index: self.pin_index(i),
                            bg=card_bg, fg=YELLOW if item.get("pinned") else MUTED,
                            activebackground=card_bg, activeforeground=ACCENT,
                            relief="flat", borderwidth=0, highlightthickness=0,
                            font=(self.ui_font, 15), cursor="hand2")
            pin.pack(side="right", padx=(8, 0))
            if selected:
                tk.Label(card, text="↵", bg=card_bg, fg=ACCENT, font=(self.ui_font, 17, "bold")).pack(side="right", padx=(10, 0))
        footer_text = self.pin_notice or "↑ ↓ navigate     Enter select     P pin     Esc close"
        tk.Label(outer, text=footer_text, bg=BG, fg=ACCENT if self.pin_notice else MUTED, font=(self.mono_font, 8, "bold" if self.pin_notice else "normal")).pack(anchor="w", pady=(12, 0))

    def select_and_activate(self, index: int) -> None:
        self.selected = index
        self.activate()

    def pin_index(self, index: int) -> None:
        items = self.filtered()
        if 0 <= index < len(items):
            items[index]["pinned"] = not items[index].get("pinned", False)
            self.pin_notice = "Pinned — saved across restarts" if items[index]["pinned"] else "Unpinned — available this session"
            self.save_history()
            self.draw()
            self.root.after(1400, self.clear_pin_notice)

    def run(self) -> None:
        self.root.mainloop()


def toggle() -> int:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(SOCKET_PATH))
        return 0
    except OSError:
        return 1


def main() -> None:
    if "--toggle" in os.sys.argv:
        raise SystemExit(toggle())
    app = ClipboardApp()
    signal.signal(signal.SIGTERM, lambda *_: app.root.after(0, app.root.destroy))
    app.run()
    SOCKET_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
