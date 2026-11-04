# Log Overlay

Real-time transparent overlay that displays the last N lines of a log file on Windows. Designed for X-Plane flight simulator but works with any text log file.

## Tech Stack

- **Python 3.9+** with **Tkinter** for GUI
- **pywin32** for Win32 API (click-through windows, hotkeys)
- **pystray + Pillow** for system tray icon (optional)
- **PyInstaller** for building standalone EXE

## Project Structure

Single-file application: `log_overlay.py` (~1100 lines) containing:
- `extract_tag()` — smart log source detection via regex (handles timestamps, bracketed plugins, bare names, X-Plane system prefixes)
- `LogTailer` — background thread that polls log file for new lines (tail -f style), stores (line, tag) tuples in a lock-protected 5000-line history buffer
- `OverlayWindow` — transparent, click-through, always-on-top Tkinter window with color-coded lines, tag-based filtering and the scroll position
- `ScrollBarWindow` — interactive scrollbar window beside the overlay
- `TagBar` — clickable tag filter bar above the overlay with ALL/WARNINGS/ERRORS/LIVE buttons + auto-populated source tags
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
- ScrollBarWindow is NOT click-through, and sits beside the overlay rather than on it because the overlay can't receive input; the overlay gives up `SCROLLBAR_WIDTH` pixels so the total stays `width`
- Mouse wheel only works over interactive windows; over the overlay it goes to X-Plane
- The tailer thread only sets a dirty flag; the main thread redraws every 100ms, so log bursts don't freeze the UI
- Scrolled views anchor to a line's sequence number, so they stay on the same lines as new ones arrive; changing a filter or rotating the log returns to live
- LogTailer uses polling (0.2s interval) — simple, cross-compatible, no file system watchers
- Handles log rotation: detects file size shrink, resets to beginning, clears all buffers and filters
- UTF-8 with error tolerance (`errors='replace'`)
- Lines truncated at 180 chars with "..."
- Error/warning detection trusts X-Plane's level prefix (`E/`, `W/`, `I/`, `D/`); lines without one use whole-word keywords (ERROR, FAIL, CRASH, WARNING, etc.)
- Tag extraction strips leading timestamps before pattern matching for robust detection
- Bracketed plugin names are normalized (paths stripped, suffixes removed)
- Top positions offset 40px down to avoid overlapping X-Plane's menu bar
- Overlay height calculated from actual font metrics to avoid empty space
- Filtering searches the full 5000-line buffer, not just visible lines
- Severity filters (WARNINGS/ERRORS) are mutually exclusive with tag filters for simple UX

## Controls

- Control bar: Hide/Show button, X to quit (draggable)
- Scrollbar: drag, arrows or mouse wheel to read older lines
- Tag bar: ALL (clear filters), WARNINGS (yellow lines only), ERRORS (red lines only), LIVE (back to the latest lines), + source tags (draggable), mouse wheel scrolls
- System tray: right-click menu (Show/Hide, Open Config, Quit)
