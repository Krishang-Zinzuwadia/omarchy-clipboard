#!/usr/bin/env bash
# Copy an entry selected by the QML overlay without interpolating clipboard data.
set -euo pipefail

[[ "${1:-}" == "--entry" ]] || exit 64
IFS= read -r payload || exit 0
[[ ${#payload} -le 100000 ]] || exit 1
kind="$(jq -r '.kind // empty' <<<"$payload")"
text="$(jq -jr '.text // empty' <<<"$payload")"
path="$(jq -r '.path // empty' <<<"$payload")"
mime="$(jq -r '.mime // "image/png"' <<<"$payload")"

case "$kind" in
  text)
    printf '%s' "$text" | wl-copy --type text/plain;charset=utf-8
    # The QML overlay closes immediately after starting this helper. Wait for
    # keyboard focus to return to the previously focused text input.
    sleep 0.15
    wtype -- "$text"
    ;;
  image)
    [[ -n "$path" && -f "$path" ]] && wl-copy --type "$mime" <"$path"
    ;;
esac
