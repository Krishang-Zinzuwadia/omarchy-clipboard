#!/usr/bin/env python3
"""Windows+V-style clipboard history for Omarchy/Hyprland."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont


APP_NAME = "Omarchy Clipboard"
BASE_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "omarchy-clipboard"
HISTORY_FILE = BASE_DIR / "history.json"
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omarchy-clipboard.sock"
MAX_ITEMS = 80
POLL_SECONDS = 0.35

BG = "#151719"
PANEL = "#202326"
PANEL_HOVER = "#2b3034"
TEXT = "#f3f4f5"
MUTED = "#9da4aa"
ACCENT = "#7dd3fc"
ACCENT_DARK = "#153449"
RED = "#fda4af"


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
        self.history: list[dict] = self.load_history()
        self.last_signature: str | None = None
        self.visible = False
        self.selected = 0
        self.query = ""
        self.server: socket.socket | None = None
        self.image_refs: list[tk.PhotoImage] = []

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
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

    def load_history(self) -> list[dict]:
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (OSError, ValueError, TypeError):
            return []

    def save_history(self) -> None:
        tmp = HISTORY_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.history, ensure_ascii=False))
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
        self.history = [x for x in self.history if not (x["kind"] == "text" and x["text"] == text)]
        self.history.insert(0, {"id": uuid.uuid4().hex, "kind": "text", "text": text, "time": time.time()})
        self.history = self.history[:MAX_ITEMS]
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
        self.history = [x for x in self.history if not (x["kind"] == "image" and x.get("signature") == signature)]
        self.history.insert(0, {"id": uuid.uuid4().hex, "kind": "image", "path": str(path), "mime": mime, "signature": signature, "time": time.time()})
        self.history = self.history[:MAX_ITEMS]
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
        if event.keysym == "BackSpace":
            self.query = self.query[:-1]
        elif len(event.char) == 1 and not (event.state & 0x4):
            self.query += event.char
        else:
            return
        self.selected = 0
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
        self.last_signature = None
        self.hide()
        return "break"

    def draw(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.image_refs.clear()
        width, height = 760, 590
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{width}x{height}+{(screen_w-width)//2}+{(screen_h-height)//2}")
        self.root.resizable(False, False)

        outer = tk.Frame(self.root, bg=BG, padx=24, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="Clipboard", bg=BG, fg=TEXT, font=("Sans", 24, "bold")).pack(anchor="w")
        tk.Label(outer, text="Super+V  ·  ↑ ↓ navigate  ·  Enter select  ·  Esc close", bg=BG, fg=MUTED, font=("Sans", 10)).pack(anchor="w", pady=(3, 16))

        search = tk.Frame(outer, bg=PANEL, height=42)
        search.pack(fill="x", pady=(0, 14))
        search.pack_propagate(False)
        tk.Label(search, text="⌕", bg=PANEL, fg=ACCENT, font=("Sans", 18)).pack(side="left", padx=(13, 7))
        tk.Label(search, text=self.query or "Type to search clipboard history", bg=PANEL, fg=TEXT if self.query else MUTED, font=("Sans", 11), anchor="w").pack(side="left", fill="both", expand=True)
        tk.Label(search, text=f"{len(self.history)} items", bg=PANEL, fg=MUTED, font=("Sans", 9)).pack(side="right", padx=14)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        items = self.filtered()
        if not items:
            tk.Label(canvas, text="Your clipboard history is empty", bg=BG, fg=MUTED, font=("Sans", 12)).pack(pady=90)
        for index, item in enumerate(items[:8]):
            selected = index == self.selected
            card = tk.Frame(canvas, bg=ACCENT_DARK if selected else PANEL, padx=14, pady=11, cursor="hand2")
            card.pack(fill="x", pady=(0, 8))
            card.bind("<Button-1>", lambda _e, i=index: self.select_and_activate(i))
            if item["kind"] == "image":
                try:
                    img = tk.PhotoImage(file=item["path"])
                    scale = max(1, img.width() // 110, img.height() // 70)
                    if scale > 1:
                        img = img.subsample(scale, scale)
                    self.image_refs.append(img)
                    tk.Label(card, image=img, bg=card["bg"]).pack(side="left", padx=(0, 14))
                    label = "Image"
                except tk.TclError:
                    label = "Image (preview unavailable)"
            else:
                label = item["text"].replace("\n", " ↵ ")
                if len(label) > 90:
                    label = label[:87] + "…"
            tk.Label(card, text=label, bg=card["bg"], fg=TEXT, font=("Sans", 11), anchor="w", justify="left", wraplength=575).pack(side="left", fill="x", expand=True)
            if selected:
                tk.Label(card, text="↵", bg=card["bg"], fg=ACCENT, font=("Sans", 16, "bold")).pack(side="right")
        tk.Label(outer, text="Clipboard history is stored locally on this device", bg=BG, fg=MUTED, font=("Sans", 9)).pack(anchor="w", pady=(10, 0))

    def select_and_activate(self, index: int) -> None:
        self.selected = index
        self.activate()

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
