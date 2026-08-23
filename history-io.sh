#!/usr/bin/env bash
# Bounded, owner-only persistence for clipboard history.
set -euo pipefail
umask 077

max_history_bytes=4194304
max_entries=300
max_text_bytes=16384
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-clipboard"
default_history="$state_dir/history.json"
action="${1:?read or write required}"
history="${2:-$default_history}"

empty_state() {
  printf '{"items":[]}\n'
}

secure_state_dir() {
  [[ ! -e "$state_dir" ]] && install -d -m 700 "$state_dir"
  [[ -d "$state_dir" && ! -L "$state_dir" && -O "$state_dir" ]] || return 1
  chmod 700 "$state_dir"
}

safe_history_file() {
  [[ -f "$history" && ! -L "$history" && -O "$history" ]] || return 1
  local bytes
  bytes="$(stat -c '%s' -- "$history")"
  (( bytes <= max_history_bytes ))
}

valid_state() {
  jq -e \
    --argjson max_entries "$max_entries" \
    --argjson max_text_bytes "$max_text_bytes" '
      type == "object" and
      ((.bootId? | type) == "string" or .bootId? == null) and
      (.items | type == "array") and
      (.items | length <= $max_entries) and
      all(.items[];
        type == "object" and
        ((.pinned? | type) == "boolean" or .pinned? == null) and
        ((.capturedAt? | type) == "number" or .capturedAt? == null) and
        if .kind == "text" then
          (.text | type == "string" and utf8bytelength <= $max_text_bytes)
        elif .kind == "image" then
          (.path | type == "string" and length <= 4096) and
          (.mime | type == "string" and length <= 128)
        else false end
      )
    ' >/dev/null
}

case "$action" in
  read)
    secure_state_dir || { empty_state; exit 0; }
    safe_history_file && valid_state <"$history" && cat -- "$history" || empty_state
    ;;
  write)
    secure_state_dir || exit 1
    tmp="$(mktemp "$state_dir/.history.XXXXXX")"
    trap 'rm -f -- "$tmp"' EXIT
    head -c "$((max_history_bytes + 1))" >"$tmp"
    (( "$(stat -c '%s' -- "$tmp")" <= max_history_bytes )) || exit 1
    valid_state <"$tmp" || exit 1
    mv -f -- "$tmp" "$history"
    trap - EXIT
    ;;
  *) exit 64 ;;
esac
