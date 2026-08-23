#!/usr/bin/env bash
# Normalize plugin state once per shell load and import the retired GTK state.
set -euo pipefail

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-clipboard"
history="$state_dir/history.json"
legacy="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-clipboard/history.json"
boot_id="$(< /proc/sys/kernel/random/boot_id)"
mkdir -p "$state_dir"

if [[ ! -f "$history" && -f "$legacy" ]]; then
  jq --arg boot "$boot_id" '
    .items // . as $items |
    {bootId:$boot, items: [
      $items[]? |
      if (.kind == "text") then
        {kind:"text", text:.text, pinned:(.pinned // false), capturedAt:(.time // now)}
      elif (.kind == "image" and (.path | type == "string")) then
        {kind:"image", path:.path, mime:(.mime // "image/png"), pinned:(.pinned // false), capturedAt:(.time // now)}
      else empty end
    ]}
  ' "$legacy" >"$history.tmp" && mv "$history.tmp" "$history"
fi

if [[ ! -f "$history" ]]; then
  printf '{"bootId":"%s","items":[]}\n' "$boot_id" >"$history"
  exit 0
fi

jq --arg boot "$boot_id" '
  if .bootId == $boot then .
  else {bootId:$boot, items:[(.items // .)[]? | select(.pinned == true)]}
  end
' "$history" >"$history.tmp" && mv "$history.tmp" "$history"
