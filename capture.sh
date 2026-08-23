#!/usr/bin/env bash
# Emit the current Wayland clipboard as one JSON history entry.
set -o pipefail

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-clipboard"
image_dir="$state_dir/images"
max_text_bytes=16384
max_image_bytes=10485760
mkdir -p -m 700 "$state_dir" "$image_dir"

types="$(wl-paste --list-types 2>/dev/null || true)"
[[ ${CLIPBOARD_STATE:-} == sensitive || "$types" == *$'x-kde-passwordManagerHint'* ]] && exit 0

emit_image() {
  local mime="$1" ext tmp hash file
  ext="${mime#image/}"; [[ "$ext" == jpeg ]] && ext=jpg
  tmp="$(mktemp --tmpdir="$image_dir" clipboard.XXXXXX)" || exit 0
  head -c "$((max_image_bytes + 1))" >"$tmp"
  [[ -s "$tmp" && "$(stat -c '%s' -- "$tmp")" -le "$max_image_bytes" ]] || { rm -f "$tmp"; exit 0; }
  hash="$(sha256sum "$tmp" | awk '{print $1}')"
  file="$image_dir/$hash.$ext"
  [[ -e "$file" ]] && rm -f "$tmp" || mv "$tmp" "$file"
  jq -cn --arg mime "$mime" --arg path "$file" \
    '{kind:"image",mime:$mime,path:$path,pinned:false,capturedAt:(now|floor)}'
}

case "${1:-}" in
  text)
    tmp="$(mktemp --tmpdir="$state_dir" clipboard-text.XXXXXX)" || exit 0
    trap 'rm -f -- "$tmp"' EXIT
    head -c "$((max_text_bytes + 1))" >"$tmp"
    [[ -s "$tmp" && "$(stat -c '%s' -- "$tmp")" -le "$max_text_bytes" ]] || exit 0
    jq -cRs 'select(length > 0) | {kind:"text",text:.,pinned:false,capturedAt:(now|floor)}' <"$tmp"
    ;;
  image/*) emit_image "$1" ;;
  *)
    for mime in image/png image/jpeg image/webp image/gif image/bmp image/tiff; do
      grep -qx "$mime" <<<"$types" && { timeout 2s wl-paste --type "$mime" 2>/dev/null | emit_image "$mime"; exit 0; }
    done
    (grep -q '^text/' <<<"$types" || grep -qx 'UTF8_STRING' <<<"$types" || grep -qx 'STRING' <<<"$types") &&
      wl-paste --type text --no-newline 2>/dev/null | "$0" text
    ;;
esac
