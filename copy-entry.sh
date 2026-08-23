#!/usr/bin/env bash
# Copy an entry selected by the QML overlay without interpolating clipboard data.
set -euo pipefail

[[ "${1:-}" == "--entry" ]] || exit 64
kind="${2:-}"
text="${3:-}"
path="${4:-}"
mime="${5:-image/png}"

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
