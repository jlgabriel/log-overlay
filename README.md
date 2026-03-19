# Log Overlay

Real-time transparent log overlay for Windows. Displays the last lines of any log file as a click-through, always-on-top overlay on your screen.

Designed for **X-Plane** flight simulator, but works with any text log file.

## Features

- Transparent, click-through overlay (doesn't interfere with your sim)
- **Smart tag filtering** — automatically detects log sources (plugins, subsystems) and displays clickable filter tags
- Filter from a deep buffer (5000 lines) so you can find relevant lines even after they scroll off screen
- Color-coded lines: red for errors, yellow for warnings
- Dynamic overlay height — window fits exactly the configured number of lines, no wasted space
- System tray icon with menu
- Auto-detects X-Plane's Log.txt location
- Configurable via `config.ini` (no command line needed)

## Quick Start (EXE)

1. Download the latest release ZIP
2. Extract to any folder
3. Edit `config.ini` and set your X-Plane log path (or leave empty for auto-detect)
4. Double-click `LogOverlay.exe`

## Quick Start (Python)

Requires Python 3.9+ on Windows.

```bash
pip install pywin32 pystray Pillow
```

Then either:
- Double-click `start_overlay.bat`
- Or run: `python log_overlay.py`

## Configuration

Edit `config.ini` next to the app. All settings are optional.

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `[log]` | `path` | *(auto-detect)* | Path to the log file |
| `[overlay]` | `lines` | `15` | Number of lines to show |
| `[overlay]` | `opacity` | `0.80` | Window opacity (0.0 - 1.0) |
| `[overlay]` | `font_size` | `11` | Font size in points |
| `[overlay]` | `position` | `bottom-right` | top-left, top-right, bottom-left, bottom-right, center |
| `[overlay]` | `width` | `1200` | Overlay width in pixels |
| `[overlay]` | `max_tags` | `20` | Maximum number of filter tags to show |
| `[overlay]` | `margin` | `20` | Margin from screen edge (px) |
| `[colors]` | `color_coding` | `true` | Enable color-coded lines |
| `[colors]` | `color_error` | `#ff6b6b` | Color for error lines |
| `[colors]` | `color_warning` | `#ffd93d` | Color for warning lines |
| `[colors]` | `color_normal` | `#e0e0e0` | Color for normal lines |
| `[colors]` | `background` | `#1a1a2e` | Background color |

CLI arguments override config.ini values:

```bash
python log_overlay.py --logfile "C:\X-Plane 12\Log.txt" --lines 20 --opacity 0.9
```

## Controls

| Action | Method |
|--------|--------|
| Quit | Control bar X button or tray menu > Quit |
| Show/Hide | Control bar Hide/Show button or tray menu > Show/Hide |
| Edit Config | Tray menu > Open Config |

## Building the EXE

To create a standalone executable:

```bash
build.bat
```

This produces `dist/LogOverlay.exe` + `dist/config.ini` ready to distribute.

## Troubleshooting

**"pywin32 is required"** - Run `pip install pywin32`

**Overlay not visible** - Check that `opacity` is not set to 0. Try `position = center` to verify it's on screen.

**Wrong log file** - Edit `config.ini` and set the correct path to your X-Plane Log.txt

**No tray icon** - Install optional dependencies: `pip install pystray Pillow`. The overlay works without them.

## License

MIT License - see [LICENSE](LICENSE)
