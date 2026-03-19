# Log Overlay

Real-time transparent overlay that displays the last N lines of a log file on Windows. Designed for X-Plane flight simulator but works with any text log file.

## Tech Stack

- **Python 3.9+** with **Tkinter** for GUI
- **pywin32** for Win32 API (click-through windows, hotkeys)
- **pystray + Pillow** for system tray icon (optional)
- **PyInstaller** for building standalone EXE

## Project Structure

Single-file application: `log_overlay.py` (~900 lines) containing:
- `extract_tag()` — smart log source detection via regex (handles timestamps, bracketed plugins, bare names, X-Plane system prefixes)
- `LogTailer` — background thread that polls log file for new lines (tail -f style), stores (line, tag) tuples in both visible and deep (5000-line) buffers
- `OverlayWindow` — transparent, click-through, always-on-top Tkinter window with color-coded lines and tag-based filtering
- `TagBar` — clickable tag filter bar above the overlay, auto-populated from log source frequency
- `ControlBar` — small draggable toolbar (Hide/Show, Close) that IS interactive
- `TrayIcon` — system tray icon with context menu (runs in daemon thread)
- `load_config()` / `auto_detect_logfile()` — config loading + X-Plane path detection
- `main()` — entry point, wires everything together

## Configuration

`config.ini` next to script/exe. Sections: `[log]`, `[overlay]`, `[colors]`. CLI args override config values.

Configurable overlay settings include: lines, opacity, font_size, position, width (default 1200px), max_tags (default 20), and margin.

## Build & Run

```bash
# Run directly
python log_overlay.py

# Build standalone EXE
build.bat   # outputs dist/LogOverlay.exe + dist/config.ini
```

## Key Design Decisions

- Window is click-through via Win32 `WS_EX_TRANSPARENT | WS_EX_LAYERED` so X-Plane receives all input
- ControlBar is NOT click-through (separate window for user interaction)
- TagBar is NOT click-through (interactive filter buttons above the overlay)
- LogTailer uses polling (0.2s interval) — simple, cross-compatible, no file system watchers
- Handles log rotation: detects file size shrink, resets to beginning
- UTF-8 with error tolerance (`errors='replace'`)
- Lines truncated at 180 chars with "..."
- Error/warning detection via keyword matching (ERROR, FAIL, CRASH, WARNING, etc.)
- Tag extraction strips leading timestamps before pattern matching for robust detection
- Bracketed plugin names are normalized (paths stripped, suffixes removed)
- Top positions offset 40px down to avoid overlapping X-Plane's menu bar
- Overlay height calculated from actual font metrics to avoid empty space
- Filtering searches the full 5000-line buffer, not just visible lines

## Hotkeys

- `Ctrl+Shift+Q` — Quit
- `Ctrl+Shift+H` — Toggle overlay visibility
