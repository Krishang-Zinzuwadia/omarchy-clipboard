# Omarchy Clipboard

Windows-style clipboard history for Omarchy on Wayland/Hyprland, built with native GTK4 for crisp system-font rendering.

## Features

- `Super+V` opens a centered clipboard history panel.
- Arrow keys navigate; `Enter` or a click selects and copies an item.
- Text and image clipboard contents are supported.
- Search by typing while the panel is open.
- Unpinned history remains available for the entire current PC session without an item cap.
- Pin items with the `☆` button or `P`; pinned items persist across restarts.
- Unpinned items are automatically cleared when the PC reboots.
- Pinned history is stored locally in `~/.local/share/omarchy-clipboard`.
- The panel automatically uses the active Omarchy theme colors.
- Selecting an item puts it back on the system clipboard, so `Ctrl+V` works everywhere, including `Ctrl+Shift+V` in terminals.
- Selecting text also types it into the previously focused text field when `wtype` is available.
- No background network access and no external runtime dependencies beyond Python, GTK4, `wl-copy`, and `wl-paste`.

## Install

```bash
./install.sh
```

The installer enables a user systemd service and adds the Omarchy user autostart entry. The Hyprland binding is kept in `~/.config/hypr/bindings.lua` so it survives Omarchy updates.

After installation, reload Hyprland:

```bash
hyprctl reload
```

## Controls

| Key | Action |
| --- | --- |
| `Super+V` | Open history |
| `↑` / `↓` | Navigate |
| `Enter` | Copy selected item and close |
| `P` or `☆` | Pin/unpin selected item |
| `Esc` | Close |
| Type / Backspace | Filter text history |

