# Omarchy Clipboard

Marketplace-ready native Omarchy Quattro overlay plugin. Its permanent ID is
`io.github.krishang-zinzuwadia.omarchy-clipboard`.

## Features

- `Super+V` toggles a centered, keyboard-focused overlay.
- Captures text plus common image MIME types, with image thumbnails and a full preview.
- `Up`, `Down`, `Left`, and `Right` wrap smoothly through the centered selection.
- `Enter` or click copies the selected item; `P` pins/unpins it.
- Pinned entries survive reboot. Unpinned entries are cleared at the next boot.
- `Delete` asks for explicit confirmation before removing a pinned entry.
- The first load imports history and image paths from the retired GTK app when available.

## Install

```bash
./install.sh
```

The installer validates the manifest and QML, installs under
`~/.config/omarchy/plugins/io.github.krishang-zinzuwadia.omarchy-clipboard`,
enables it in `~/.config/omarchy/shell.json`, replaces the `Super+V` binding,
disables stock `omarchy.clipboard`, rescans the shell, and then retires the GTK
user service/autostart entry.

## Remove

```bash
omarchy plugin disable io.github.krishang-zinzuwadia.omarchy-clipboard
rm -rf ~/.config/omarchy/plugins/io.github.krishang-zinzuwadia.omarchy-clipboard
```

Restore a preferred clipboard binding in `~/.config/hypr/bindings.lua`, then
run `hyprctl reload`. History is retained in
`~/.local/state/omarchy-clipboard`; remove that directory separately only if
you want to erase saved pinned entries and captured images.

## Dependencies

Omarchy Quattro / `omarchy-shell`, Quickshell, `wl-clipboard` (`wl-copy` and
`wl-paste`), `jq`, `setpriv` (util-linux), and `qmllint` for development
validation. The install script also uses `hyprctl` to apply the binding.

## Privacy

Clipboard text and images are processed locally. The plugin makes no network
requests. Captured images and history are stored only under
`~/.local/state/omarchy-clipboard`. Avoid copying secrets: the capture helper
honors the KDE password-manager clipboard hint.

## Controls

`Super+V` opens, arrows navigate, `Enter` copies, `P` toggles a pin, `Delete`
removes (with confirmation for pinned entries), and `Esc` closes or clears the
current filter.

