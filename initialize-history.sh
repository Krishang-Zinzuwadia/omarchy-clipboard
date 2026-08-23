#!/usr/bin/env bash
# Normalize plugin state once per shell load and import the retired GTK state.
set -euo pipefail

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-clipboard"
history="$state_dir/history.json"
legacy="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-clipboard/history.json"
boot_id="$(< /proc/sys/kernel/random/boot_id)"
io="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/history-io.sh"
max_history_bytes=4194304
mkdir -p -m 700 "$state_dir"

safe_input() {
  [[ -f "$1" && ! -L "$1" && -O "$1" && "$(stat -c '%s' -- "$1")" -le "$max_history_bytes" ]]
}

if [[ ! -f "$history" ]] && safe_input "$legacy"; then
  jq -c --arg boot "$boot_id" '
    .items // . as $items |
    {bootId:$boot, items: [
      $items[]? |
      if (.kind == "text") then
        {kind:"text", text:.text, pinned:(.pinned // false), capturedAt:(.time // now)}
      elif (.kind == "image" and (.path | type == "string")) then
        {kind:"image", path:.path, mime:(.mime // "image/png"), pinned:(.pinned // false), capturedAt:(.time // now)}
      else empty end
    ]}
  ' "$legacy" | "$io" write
fi

{
  "$io" read
} | jq -c --arg boot "$boot_id" '
  if .bootId == $boot then .
  else {bootId:$boot, items:[(.items // .)[]? | select(.pinned == true)]}
  end
' | "$io" write
