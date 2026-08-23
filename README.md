# Omarchy Clipboard

A native Omarchy Quattro clipboard-history overlay with session history and
reboot-persistent pins.

## Highlights

- `Super+V` opens a keyboard-focused clipboard overlay.
- Text and PNG image clipboard entries are captured locally, with image thumbnails.
- Arrow-key navigation wraps and keeps the active item visible.
- `Enter` restores the selected item to the system clipboard. For text, it also
  inserts the selection into the previously focused text input.
- Pin entries with `P`; pinned entries survive reboots while unpinned entries
  are cleared at the next boot.
- `Delete` removes entries and asks for confirmation before deleting a pin.

## Requirements

- Omarchy Quattro / `omarchy-shell` and Quickshell
- `wl-clipboard` (`wl-copy`, `wl-paste`), `jq`, and util-linux (`setpriv`)
- `hyprctl` for installing the `Super+V` binding

`qmllint` is only required when validating development changes.

## Install

Install, enable, and configure the plugin with one command:

```bash
omarchy plugin add https://github.com/Krishang-Zinzuwadia/omarchy-clipboard.git --enable && "$HOME/.config/omarchy/plugins/io.github.krishang-zinzuwadia.omarchy-clipboard/install.sh"
```

`omarchy plugin add` shows Omarchy's trust confirmation before it clones and
enables the public repository. The local helper then configures the plugin in
`~/.config/omarchy/plugins/io.github.krishang-zinzuwadia.omarchy-clipboard`,
disables Omarchy's stock clipboard plugin, and assigns `Super+V`.
It updates only user-owned Omarchy/Hyprland configuration, requires no elevated
privileges, and does not download or execute code outside this repository.

For local development from a checkout, run `./install.sh` instead.

## Usage

| Key | Action |
| --- | --- |
| `Super+V` | Open or close clipboard history |
| `↑` `↓` `←` `→` | Navigate entries |
| `Enter` | Copy the selected entry; insert selected text into the prior input |
| `P` | Pin or unpin the selected entry |
| `Delete` | Remove the selected entry |
| `Esc` | Close the overlay or clear the active filter |

## Remove

```bash
PLUGIN_ID=io.github.krishang-zinzuwadia.omarchy-clipboard
omarchy plugin disable "$PLUGIN_ID"
rm -rf "$HOME/.config/omarchy/plugins/$PLUGIN_ID"
hyprctl reload
```

Removal leaves clipboard history at `~/.local/state/omarchy-clipboard` and
leaves the `Super+V` binding choice to you. Delete saved history and images
only if you want to erase them permanently:

```bash
rm -rf "$HOME/.local/state/omarchy-clipboard"
```

To return to Omarchy's stock clipboard plugin, re-enable it and configure its
preferred keybinding:

```bash
omarchy plugin enable omarchy.clipboard
```

## Privacy

Clipboard text and images are processed locally; this plugin makes no network
requests. Avoid copying secrets when clipboard history is enabled. The capture
helper honors the KDE password-manager clipboard hint.

## Development

```bash
omarchy plugin validate .
qmllint Clipboard.qml
```

Plugin ID: `io.github.krishang-zinzuwadia.omarchy-clipboard`
License: [MIT](LICENSE)

