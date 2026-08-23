#!/usr/bin/env bash
# Copy an entry selected by the QML overlay without interpolating clipboard data.
set -euo pipefail

[[ "${1:-}" == "--entry" ]] || exit 64
IFS= read -r payload || exit 0
[[ ${#payload} -le 100000 ]] || exit 1
kind="$(jq -r '.kind // empty' <<<"$payload")"
path="$(jq -r '.path // empty' <<<"$payload")"
mime="$(jq -r '.mime // "image/png"' <<<"$payload")"

case "$kind" in
  text)
    # Selection paste is single-line so multiline history entries cannot submit
    # forms or create unintended commands in the target application.
    printf '%s' "$payload" | jq -jr '(.text // empty) | gsub("[\\r\\n]+"; " ")' | wl-copy --type text/plain;charset=utf-8
    ;;
  image)
    [[ -n "$path" && -f "$path" ]] && wl-copy --type "$mime" <"$path"
    ;;
esac
