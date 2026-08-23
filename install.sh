#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ID="io.github.krishang-zinzuwadia.omarchy-clipboard"
PLUGIN_DIR="$HOME/.config/omarchy/plugins/$ID"

omarchy plugin validate "$ROOT"
command -v qmllint >/dev/null && qmllint "$ROOT/Clipboard.qml"

mkdir -p "$PLUGIN_DIR"
# `omarchy plugin add` already clones this repository into PLUGIN_DIR. Avoid
# copying files onto themselves so the same helper supports that install path.
if [[ "$(realpath "$ROOT")" != "$(realpath "$PLUGIN_DIR")" ]]; then
  install -m 0644 "$ROOT/manifest.json" "$ROOT/Clipboard.qml" "$ROOT/ClipboardHistory.js" "$ROOT/history-io.py" "$PLUGIN_DIR/"
  install -m 0755 "$ROOT/capture.sh" "$ROOT/copy-entry.sh" "$ROOT/history-io.sh" "$ROOT/initialize-history.sh" "$PLUGIN_DIR/"
fi

python3 - "$HOME/.config/omarchy/shell.json" "$ID" <<'PY'
import json
from pathlib import Path
import sys
path, plugin_id = map(Path, sys.argv[1:3])
data = json.loads(path.read_text()) if path.exists() else {"version": 1}
plugins = [p for p in data.get("plugins", []) if (p.get("id") if isinstance(p, dict) else p) != "omarchy.clipboard"]
if not any((p.get("id") if isinstance(p, dict) else p) == str(plugin_id) for p in plugins):
    plugins.append({"id": str(plugin_id), "enabled": True})
data["plugins"] = plugins
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n")
tmp.replace(path)
PY

python3 - "$HOME/.config/hypr/bindings.lua" "$ID" <<'PY'
from pathlib import Path
import sys
path, plugin_id = map(Path, sys.argv[1:3])
text = path.read_text() if path.exists() else ""
lines = [line for line in text.splitlines() if "omarchy-clipboard --toggle" not in line and "org.omarchy.Clipboard" not in line]
lines = [line for line in lines if not ('SUPER + V' in line and 'shell toggle' in line)]
if not any('hl.unbind("SUPER + V")' in line for line in lines):
    lines += ['hl.unbind("SUPER + V")']
lines += ['-- Omarchy Clipboard overlay', f'o.bind("SUPER + V", "Clipboard history", "omarchy-shell shell toggle {plugin_id}")']
path.write_text("\n".join(lines).rstrip() + "\n")
PY

omarchy plugin disable omarchy.clipboard
omarchy-shell shell rescanPlugins
omarchy plugin list --json | jq -e --arg id "$ID" '.[] | select(.id == $id and .enabled == true)' >/dev/null
# A successful IPC toggle verifies that the shell has loaded the overlay before
# the legacy GTK daemon is retired. Toggle again to leave it closed.
omarchy shell shell toggle "$ID"
omarchy shell shell toggle "$ID"

# The native overlay is now discoverable and enabled. Retire only the old
# background process; its state remains as a one-time migration source.
systemctl --user disable --now omarchy-clipboard.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/omarchy-clipboard.service"
python3 - "$HOME/.config/hypr/autostart.lua" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
if path.exists():
    lines = [line for line in path.read_text().splitlines() if "omarchy-clipboard.service" not in line and "Omarchy Clipboard history" not in line]
    path.write_text("\n".join(lines).rstrip() + "\n")
PY
systemctl --user daemon-reload
hyprctl reload
printf 'Installed and enabled %s. Super+V now toggles the Omarchy shell overlay.\n' "$ID"
