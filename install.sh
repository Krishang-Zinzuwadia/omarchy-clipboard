#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
install -m 0755 "$ROOT/omarchy-clipboard" "$HOME/.local/bin/omarchy-clipboard"
install -m 0644 "$ROOT/omarchy-clipboard.service" "$HOME/.config/systemd/user/omarchy-clipboard.service"

python3 - "$HOME/.config/hypr/autostart.lua" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text() if p.exists() else ""
line = 'o.launch_on_start("systemctl --user start omarchy-clipboard.service")'
if line not in s:
    p.write_text(s.rstrip() + "\n\n-- Omarchy Clipboard history\n" + line + "\n")
PY

systemctl --user daemon-reload
systemctl --user enable --now omarchy-clipboard.service
printf 'Installed Omarchy Clipboard daemon. Add the Super+V binding, then reload Hyprland.\n'
