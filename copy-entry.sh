#!/usr/bin/env bash
# Copy an entry selected by the QML overlay without interpolating clipboard data.
set -euo pipefail

history_file="${1:?history file required}"
index="${2:?history index required}"
io="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/history-io.sh"
kind="$("$io" read "$history_file" | jq -r ".items[$index].kind // empty")"

case "$kind" in
  text)
    text="$("$io" read "$history_file" | jq -jr ".items[$index].text")"
    printf '%s' "$text" | wl-copy --type text/plain;charset=utf-8
    # The QML overlay closes immediately after starting this helper. Wait for
    # keyboard focus to return to the previously focused text input.
    sleep 0.15
    wtype -- "$text"
    ;;
  image)
    mime="$("$io" read "$history_file" | jq -r ".items[$index].mime // \"image/png\"")"
    path="$("$io" read "$history_file" | jq -r ".items[$index].path // empty")"
    [[ -n "$path" && -f "$path" ]] && wl-copy --type "$mime" <"$path"
    ;;
esac
