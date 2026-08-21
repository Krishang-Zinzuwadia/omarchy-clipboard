# Omarchy Clipboard

Windows-style clipboard history for Omarchy on Wayland/Hyprland.

## Features

- `Super+V` opens a centered clipboard history panel.
- Arrow keys navigate; `Enter` or a click selects and copies an item.
- Text and image clipboard contents are supported.
- Search by typing while the panel is open.
- History persists locally in `~/.local/share/omarchy-clipboard`.
- Selecting an item puts it back on the system clipboard, so `Ctrl+V` works everywhere, including `Ctrl+Shift+V` in terminals.
- No background network access and no external runtime dependencies beyond Python, Tk, `wl-copy`, and `wl-paste`.

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
| `Esc` | Close |
| Type / Backspace | Filter text history |

