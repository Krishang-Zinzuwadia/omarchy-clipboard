#!/usr/bin/env bash
# Copy an entry selected by the QML overlay without interpolating clipboard data.
set -euo pipefail

history_file="${1:?history file required}"
index="${2:?history index required}"
kind="$(jq -r ".items[$index].kind // empty" "$history_file")"

case "$kind" in
  text)
    text="$(jq -jr ".items[$index].text" "$history_file")"
    printf '%s' "$text" | wl-copy --type text/plain;charset=utf-8
    # The QML overlay closes immediately after starting this helper. Wait for
    # keyboard focus to return to the previously focused text input.
    sleep 0.15
    wtype -- "$text"
    ;;
  image)
    mime="$(jq -r ".items[$index].mime // \"image/png\"" "$history_file")"
    path="$(jq -r ".items[$index].path // empty" "$history_file")"
    [[ -n "$path" && -f "$path" ]] && wl-copy --type "$mime" <"$path"
    ;;
esac
