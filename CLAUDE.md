# Log Overlay

Real-time transparent overlay that displays the last N lines of a log file on Windows. Designed for X-Plane flight simulator but works with any text log file.

## Tech Stack

- **Python 3.9+** with **Tkinter** for GUI
- **pywin32** for Win32 API (click-through windows, hotkeys)
- **pystray + Pillow** for system tray icon (optional)
- **PyInstaller** for building standalone EXE

## Project Structure

Single-file application: `log_overlay.py` (~637 lines) containing:
- `LogTailer` — background thread that polls log file for new lines (tail -f style)
- `OverlayWindow` — transparent, click-through, always-on-top Tkinter window with color-coded lines
- `ControlBar` — small draggable toolbar (Hide/Show, Close) that IS interactive
- `TrayIcon` — system tray icon with context menu (runs in daemon thread)
- `load_config()` / `auto_detect_logfile()` — config loading + X-Plane path detection
- `main()` — entry point, wires everything together

## Configuration

`config.ini` next to script/exe. Sections: `[log]`, `[overlay]`, `[colors]`. CLI args override config values.

Configurable overlay settings include: lines, opacity, font_size, position, width (default 1200px), and margin.

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
- LogTailer uses polling (0.2s interval) — simple, cross-compatible, no file system watchers
- Handles log rotation: detects file size shrink, resets to beginning
- UTF-8 with error tolerance (`errors='replace'`)
- Lines truncated at 180 chars with "..."
- Error/warning detection via keyword matching (ERROR, FAIL, CRASH, WARNING, etc.)

## Hotkeys

- `Ctrl+Shift+Q` — Quit
- `Ctrl+Shift+H` — Toggle overlay visibility
