"""
Log Overlay for Windows
========================
Displays the last lines of a log file as a transparent, always-on-top,
click-through overlay on your screen. Designed for X-Plane flight simulator
but works with any log file.

Usage:
    python log_overlay.py
    python log_overlay.py --logfile "C:\\X-Plane 12\\Log.txt"
    python log_overlay.py --lines 20 --opacity 0.85

Configuration:
    Edit config.ini next to this script to set defaults.
    CLI arguments override config.ini values.

Controls:
    Control bar    -> Drag to move, Hide/Show, X to quit
    System tray    -> Right-click for menu
"""

import sys
import os
import re
import time
import argparse
import threading
import configparser
import subprocess
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
from collections import deque

# --- Win32 imports for click-through ---
try:
    import win32gui
    import win32con
    import win32api
except ImportError:
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Log Overlay - Missing Dependency",
            "pywin32 is required but not installed.\n\n"
            "Install it with:\n  pip install pywin32\n\n"
            "Then restart the application."
        )
        root.destroy()
    except Exception:
        print("ERROR: pywin32 is required. Install it with:")
        print("  pip install pywin32")
    sys.exit(1)

# --- Optional: System tray icon ---
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


# --- Helpers ---

def get_app_dir():
    """Return the directory where the app/exe lives."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def auto_detect_xplane_log():
    """Try to find X-Plane's Log.txt in common locations."""
    candidates = [
        os.path.join("C:\\", "X-Plane 12", "Log.txt"),
        os.path.join("C:\\", "X-Plane 11", "Log.txt"),
        os.path.join("D:\\", "X-Plane 12", "Log.txt"),
        os.path.join("D:\\", "X-Plane 11", "Log.txt"),
        os.path.join("C:\\", "Program Files (x86)", "Steam", "steamapps",
                      "common", "X-Plane 12", "Log.txt"),
        os.path.join("C:\\", "Program Files (x86)", "Steam", "steamapps",
                      "common", "X-Plane 11", "Log.txt"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def load_config(cli_args):
    """Load settings from config.ini, with CLI args taking priority."""
    defaults = {
        "logfile": "",
        "lines": 15,
        "opacity": 0.80,
        "font_size": 11,
        "position": "bottom-right",
        "margin": 20,
        "width": 1200,
        "max_tags": 20,
        "color_coding": True,
        "color_error": "#ff6b6b",
        "color_warning": "#ffd93d",
        "color_normal": "#e0e0e0",
        "background": "#1a1a2e",
    }

    config_path = os.path.join(get_app_dir(), "config.ini")
    if os.path.isfile(config_path):
        cp = configparser.ConfigParser()
        cp.read(config_path, encoding="utf-8")

        if cp.has_option("log", "path"):
            val = cp.get("log", "path").strip()
            if val:
                defaults["logfile"] = val
        for key in ["lines", "opacity", "font_size", "margin", "width", "max_tags"]:
            if cp.has_option("overlay", key):
                val = cp.get("overlay", key).strip()
                if val:
                    if key in ("opacity",):
                        defaults[key] = float(val)
                    else:
                        defaults[key] = int(val)
        if cp.has_option("overlay", "position"):
            defaults["position"] = cp.get("overlay", "position").strip()
        if cp.has_option("colors", "color_coding"):
            defaults["color_coding"] = cp.getboolean("colors", "color_coding")
        for key in ["color_error", "color_warning", "color_normal", "background"]:
            if cp.has_option("colors", key):
                defaults[key] = cp.get("colors", key).strip()

    # CLI overrides
    if cli_args.logfile:
        defaults["logfile"] = cli_args.logfile
    if cli_args.lines is not None:
        defaults["lines"] = cli_args.lines
    if cli_args.opacity is not None:
        defaults["opacity"] = cli_args.opacity
    if cli_args.font_size is not None:
        defaults["font_size"] = cli_args.font_size
    if cli_args.position is not None:
        defaults["position"] = cli_args.position

    # Auto-detect if no log path configured
    if not defaults["logfile"]:
        detected = auto_detect_xplane_log()
        if detected:
            defaults["logfile"] = detected
            print(f"  Auto-detected X-Plane log: {detected}")

    return defaults


# --- Tag Extraction ---

# Strip leading timestamps: "0:00:00.000 " or "2026-03-18 23:34:18 " or "2026-03-18T23:07:49.063 "
_RE_TIMESTAMP = re.compile(
    r'^(?:\d+:\d+:\d+\.\d+\s+'           # X-Plane style: 0:00:00.000
    r'|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\d.,]*\s*'  # ISO style: 2026-03-18T23:07:49.063 or 2026-03-18 23:34:18
    r')'
)

# Precompiled patterns for log source extraction (applied after timestamp strip)
_RE_XPLANE_SYS = re.compile(r'^[IEWD]/([^:]+):')
_RE_BRACKET_PLUGIN = re.compile(r'^\[([^\]]+)\]')
_RE_BARE_PLUGIN = re.compile(r'^([A-Za-z][\w.:-]*[\w])[\[: (]')

# Words that look like plugin names but are generic log content
_BARE_FALSE_POSITIVES = frozenset((
    'Loaded', 'Fetching', 'Queue', 'Heap', 'Memory', 'Vulkan',
    'OpenGL', 'Windows', 'This', 'CPU', 'Physical', 'Maximum',
    'Compiled', 'Device', 'Host', 'Log', 'Global',
    'Custom', 'Resources', 'Discovered', 'Created', 'Picked',
    'WARNING', 'ERROR', 'INFO', 'DEBUG', 'FATAL',
))


def _clean_bracket_name(name):
    """Normalize a bracketed tag name: strip paths, suffixes, level indicators."""
    # Take first segment before '/' to strip paths (XPUIPC/64/win.xpl -> XPUIPC)
    if '/' in name:
        name = name.split('/')[0]
    # Remove .xpl extension
    if name.lower().endswith('.xpl'):
        name = name[:-4]
    # Remove trailing level indicators (INFO, WARN, etc.)
    for suffix in (' INFO', ' WARN', ' ERROR', ' DEBUG'):
        if name.upper().endswith(suffix):
            name = name[:len(name) - len(suffix)].strip()
            break
    return name


def extract_tag(line):
    """Extract the source tag from a log line.

    Returns a short string identifying the source, e.g. 'GFX', 'APT',
    'XJet', 'FlyWithLua', or 'OTHER' if no pattern matches.
    """
    # Step 0: Strip leading timestamp so all patterns work on the "meat"
    stripped = _RE_TIMESTAMP.sub('', line)

    # Pattern 1: X-Plane system  e.g. "I/GFX/VK: ..." (after timestamp strip)
    m = _RE_XPLANE_SYS.match(stripped)
    if m:
        source = m.group(1)
        return source.split('/')[0].upper()

    # Pattern 2: Bracketed plugin  e.g. "[XJet] ...", "[XPUIPC/64/win.xpl]: ..."
    m = _RE_BRACKET_PLUGIN.match(stripped)
    if m:
        name = _clean_bracket_name(m.group(1).strip())
        if name:
            return name

    # Pattern 3: Bare plugin name  e.g. "X-Camera: ...", "ERJ_FMS[fms:c:1576]: ..."
    m = _RE_BARE_PLUGIN.match(stripped)
    if m:
        name = m.group(1)
        if name not in _BARE_FALSE_POSITIVES:
            return name

    return 'OTHER'


# --- Log Tailer ---

class LogTailer:
    """Reads a log file in real-time (similar to tail -f)."""

    def __init__(self, filepath, max_lines=15, callback=None):
        self.filepath = filepath
        self.max_lines = max_lines
        self.callback = callback
        self.lines = deque(maxlen=max_lines)       # stores (line_text, tag) tuples
        self.all_lines = deque(maxlen=5000)         # larger buffer for tag counting
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._tail, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _tail(self):
        """Open the file, seek to end, and poll for new lines."""
        while not os.path.exists(self.filepath):
            if self._stop_event.is_set():
                return
            time.sleep(0.5)

        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            self._read_last_lines(f)
            if self.callback:
                self.callback(list(self.lines))

            f.seek(0, 2)

            while not self._stop_event.is_set():
                line = f.readline()
                if line:
                    clean = line.rstrip("\n\r")
                    if clean:
                        entry = (clean, extract_tag(clean))
                        self.lines.append(entry)
                        self.all_lines.append(entry)
                        if self.callback:
                            self.callback(list(self.lines))
                else:
                    try:
                        current_pos = f.tell()
                        file_size = os.path.getsize(self.filepath)
                        if file_size < current_pos:
                            f.seek(0)
                            self.lines.clear()
                    except OSError:
                        pass
                    time.sleep(0.2)

    def _read_last_lines(self, f):
        """Read the last N lines of the file on startup."""
        f.seek(0, 2)
        file_size = f.tell()
        if file_size == 0:
            return

        block_size = 4096
        blocks = []
        remaining = file_size

        while remaining > 0 and len(blocks) < 10:
            read_size = min(block_size, remaining)
            f.seek(remaining - read_size)
            blocks.insert(0, f.read(read_size))
            remaining -= read_size

        text = "".join(blocks)
        all_file_lines = text.splitlines()

        # Load ALL lines into the big buffer for tag counting / filtering
        for line in all_file_lines:
            if line.strip():
                entry = (line, extract_tag(line))
                self.all_lines.append(entry)

        # Only the last N into the visible buffer
        for entry in list(self.all_lines)[-self.max_lines:]:
            self.lines.append(entry)


# --- Overlay Window ---

class OverlayWindow:
    """Transparent, always-on-top, click-through overlay window."""

    def __init__(self, config):
        self.config = config
        self.max_lines = config["lines"]
        self.visible = True
        self.active_tags = set()    # empty = show all
        self._last_lines = []       # raw (line, tag) tuples from tailer
        self.tag_bar = None         # set after TagBar is created
        self.tailer = None          # set after LogTailer is created

        bg = config["background"]

        # --- Create Tkinter window ---
        self.root = tk.Tk()
        self.root.title("Log Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", config["opacity"])
        self.root.configure(bg=bg)

        # Frame
        self.frame = tk.Frame(self.root, bg=bg, padx=10, pady=8)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Text widget for color-coded log lines
        self.mono_font = tkfont.Font(family="Consolas", size=config["font_size"])
        self.text = tk.Text(
            self.frame,
            font=self.mono_font,
            fg=config["color_normal"],
            bg=bg,
            wrap=tk.NONE,
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            cursor="arrow",
            state=tk.DISABLED,
            height=self.max_lines,
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        # Color tags
        self.text.tag_configure("error", foreground=config["color_error"])
        self.text.tag_configure("warning", foreground=config["color_warning"])
        self.text.tag_configure("normal", foreground=config["color_normal"])

        # Status bar
        status_font = tkfont.Font(family="Consolas", size=config["font_size"] - 2)
        self.status_label = tk.Label(
            self.frame,
            text="",
            font=status_font,
            fg="#555577",
            bg=bg,
            anchor="w",
        )
        self.status_label.pack(fill=tk.X)

        # Position the window
        self.root.update_idletasks()
        self._position_window()

        # Make click-through after window is shown
        self.root.after(100, self._make_click_through)

    def _position_window(self):
        """Position the window in the chosen screen corner."""
        width = self.config["width"]

        # Calculate height from actual font metrics
        line_height = self.mono_font.metrics("linespace")
        # Text lines + status bar + padding (frame pady=8 top+bottom, plus status label)
        status_height = (self.config["font_size"] - 2) + 8
        height = (self.max_lines * line_height) + status_height + 16 + 4

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        m = self.config["margin"]

        # Extra top offset to avoid overlapping X-Plane's menu bar (~40px)
        top_offset = 40
        positions = {
            "top-left":     (m, m + top_offset),
            "top-right":    (screen_w - width - m, m + top_offset),
            "bottom-left":  (m, screen_h - height - m - 40),
            "bottom-right": (screen_w - width - m, screen_h - height - m - 40),
            "center":       ((screen_w - width) // 2, (screen_h - height) // 2),
        }

        x, y = positions.get(self.config["position"], positions["bottom-right"])
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _make_click_through(self):
        """Make the window click-through using Win32 API."""
        hwnd = self.root.winfo_id()
        try:
            parent = win32gui.GetParent(hwnd)
            if parent != 0:
                hwnd = parent
        except Exception:
            pass

        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            style |= win32con.WS_EX_LAYERED
            style |= win32con.WS_EX_TRANSPARENT
            style |= win32con.WS_EX_TOPMOST
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
        except Exception as e:
            print(f"Warning: Could not enable click-through: {e}")
            print("The overlay will work but may capture mouse clicks.")

    def _classify_line(self, line):
        """Return the tag name for a log line based on its content."""
        if not self.config["color_coding"]:
            return "normal"
        upper = line.upper()
        if any(kw in upper for kw in ("ERROR", "FAIL", "CRASH", "EXCEPTION", "FATAL")):
            return "error"
        if any(kw in upper for kw in ("WARNING", "WARN", "W/", "CAUTION")):
            return "warning"
        return "normal"

    def update_text(self, lines_with_tags):
        """Update the displayed text (thread-safe via root.after).

        Args:
            lines_with_tags: list of (line_text, source_tag) tuples from tailer.lines (visible).
        """
        self._last_lines = lines_with_tags

        def _update():
            # When filtering, search the full buffer for matching lines
            if self.active_tags and self.tailer:
                all_matching = [(l, t) for l, t in self.tailer.all_lines if t in self.active_tags]
                visible = all_matching[-self.max_lines:]
            else:
                visible = lines_with_tags

            self.text.config(state=tk.NORMAL)
            self.text.delete("1.0", tk.END)
            if visible:
                for i, (line, _src_tag) in enumerate(visible):
                    if len(line) > 180:
                        line = line[:177] + "..."
                    color_tag = self._classify_line(line)
                    if i > 0:
                        self.text.insert(tk.END, "\n")
                    self.text.insert(tk.END, line, color_tag)
            else:
                self.text.insert(tk.END, "(no matching lines)", "normal")
            self.text.see(tk.END)
            self.text.xview_moveto(0)
            self.text.config(state=tk.DISABLED)

            # Update tag bar counts from the full buffer
            if self.tag_bar and self.tailer:
                self.tag_bar.update_tags(list(self.tailer.all_lines))
            elif self.tag_bar:
                self.tag_bar.update_tags(lines_with_tags)

        self.root.after(0, _update)

    def set_filter(self, tags):
        """Set active filter tags. Empty set = show all."""
        self.active_tags = tags
        if self._last_lines:
            self.update_text(self._last_lines)

    def set_status(self, text):
        """Update the status bar text."""
        def _update():
            self.status_label.config(text=text)
        self.root.after(0, _update)

    def toggle_visibility(self):
        """Show or hide the overlay and tag bar."""
        if self.visible:
            self.root.withdraw()
            if self.tag_bar:
                self.tag_bar.win.withdraw()
        else:
            self.root.deiconify()
            if self.tag_bar:
                self.tag_bar.win.deiconify()
        self.visible = not self.visible

    def quit(self):
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# --- Tag Filter Bar ---

class TagBar:
    """Clickable tag bar above the overlay for filtering log sources."""

    def __init__(self, overlay):
        self.overlay = overlay
        self.max_tags = overlay.config.get("max_tags", 20)
        self._active = set()        # currently selected tags
        self._buttons = {}          # tag -> Button widget
        self._known_tags = []       # ordered list of top tags

        bg = "#1a1a2e"
        self.win = tk.Toplevel(overlay.root)
        self.win.title("Log Tags")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.90)
        self.win.configure(bg=bg)

        self._frame = tk.Frame(self.win, bg=bg, padx=4, pady=3)
        self._frame.pack(fill=tk.X)

        self._btn_font = tkfont.Font(family="Consolas", size=8)

        # ALL button (always present)
        self._all_btn = tk.Button(
            self._frame, text="ALL", font=self._btn_font,
            fg="#e0e0e0", bg="#3a3a6e", activebackground="#4a4a7e",
            activeforeground="#ffffff", relief=tk.FLAT, padx=6, pady=1,
            command=self._clear_filter,
        )
        self._all_btn.pack(side=tk.LEFT, padx=2)

        # Position near the overlay
        self.win.update_idletasks()
        self._position()

        # Enable dragging
        self._drag_data = {"x": 0, "y": 0}
        self.win.bind("<Button-1>", self._on_drag_start)
        self.win.bind("<B1-Motion>", self._on_drag_motion)
        self._frame.bind("<Button-1>", self._on_drag_start)
        self._frame.bind("<B1-Motion>", self._on_drag_motion)

    def _position(self):
        """Position the tag bar just above the overlay window."""
        overlay_x = self.overlay.root.winfo_x()
        overlay_y = self.overlay.root.winfo_y()
        bar_h = self.win.winfo_reqheight()
        self.win.geometry(f"+{overlay_x}+{max(0, overlay_y - bar_h - 2)}")

    def update_tags(self, lines_with_tags):
        """Rebuild tag buttons based on frequency in the current lines."""
        # Count tags
        counts = {}
        for _line, tag in lines_with_tags:
            counts[tag] = counts.get(tag, 0) + 1

        # Sort by frequency, take top N (exclude OTHER from ranking unless it's all we have)
        ranked = sorted(counts.keys(), key=lambda t: counts[t], reverse=True)
        top = [t for t in ranked if t != 'OTHER'][:self.max_tags]
        if 'OTHER' in counts and len(top) < self.max_tags:
            top.append('OTHER')

        if top == self._known_tags:
            # Just update visual state, no rebuild needed
            self._refresh_button_styles()
            return

        self._known_tags = top

        # Destroy old buttons (except ALL)
        for btn in self._buttons.values():
            btn.destroy()
        self._buttons.clear()

        # Create new buttons
        for tag in top:
            btn = tk.Button(
                self._frame, text=tag, font=self._btn_font,
                fg="#888899", bg="#2a2a4e", activebackground="#3a3a5e",
                activeforeground="#ffffff", relief=tk.FLAT, padx=6, pady=1,
                command=lambda t=tag: self._toggle_tag(t),
            )
            btn.pack(side=tk.LEFT, padx=1)
            self._buttons[tag] = btn

        self._refresh_button_styles()
        self.win.update_idletasks()

    def _toggle_tag(self, tag):
        """Toggle a single tag filter on/off."""
        if tag in self._active:
            self._active.discard(tag)
        else:
            self._active.add(tag)
        self._refresh_button_styles()
        self.overlay.set_filter(set(self._active))

    def _clear_filter(self):
        """Clear all filters (show all lines)."""
        self._active.clear()
        self._refresh_button_styles()
        self.overlay.set_filter(set())

    def _refresh_button_styles(self):
        """Update button colors based on active state."""
        has_filter = bool(self._active)
        # ALL button
        if has_filter:
            self._all_btn.config(fg="#888899", bg="#2a2a4e")
        else:
            self._all_btn.config(fg="#e0e0e0", bg="#3a3a6e")

        for tag, btn in self._buttons.items():
            if tag in self._active:
                btn.config(fg="#ffffff", bg="#4a6a9e")
            else:
                btn.config(fg="#888899", bg="#2a2a4e")

    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event):
        x = self.win.winfo_x() + (event.x - self._drag_data["x"])
        y = self.win.winfo_y() + (event.y - self._drag_data["y"])
        self.win.geometry(f"+{x}+{y}")


# --- Control Bar (small floating toolbar with buttons) ---

class ControlBar:
    """Small floating toolbar with Close/Hide buttons. NOT click-through."""

    def __init__(self, overlay):
        self.overlay = overlay
        bg = "#1a1a2e"

        self.win = tk.Toplevel(overlay.root)
        self.win.title("Log Overlay Controls")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.90)
        self.win.configure(bg=bg)

        frame = tk.Frame(self.win, bg=bg, padx=4, pady=3)
        frame.pack()

        btn_font = tkfont.Font(family="Consolas", size=9)

        # Title label
        tk.Label(
            frame, text="LOG", font=btn_font,
            fg="#555577", bg=bg,
        ).pack(side=tk.LEFT, padx=(2, 6))

        # Hide/Show button
        self._toggle_btn = tk.Button(
            frame, text="Hide", font=btn_font,
            fg="#e0e0e0", bg="#2a2a4e", activebackground="#3a3a5e",
            activeforeground="#ffffff", relief=tk.FLAT, padx=8, pady=1,
            command=self._toggle,
        )
        self._toggle_btn.pack(side=tk.LEFT, padx=2)

        # Close button
        tk.Button(
            frame, text="X", font=btn_font,
            fg="#ff6b6b", bg="#2a2a4e", activebackground="#4a2a2e",
            activeforeground="#ff9999", relief=tk.FLAT, padx=6, pady=1,
            command=self.overlay.quit,
        ).pack(side=tk.LEFT, padx=2)

        # Position the bar above the overlay
        self.win.update_idletasks()
        self._position()

        # Enable dragging
        self._drag_data = {"x": 0, "y": 0}
        self.win.bind("<Button-1>", self._on_drag_start)
        self.win.bind("<B1-Motion>", self._on_drag_motion)
        frame.bind("<Button-1>", self._on_drag_start)
        frame.bind("<B1-Motion>", self._on_drag_motion)

    def _position(self):
        """Position the control bar near the overlay."""
        cfg = self.overlay.config
        m = cfg["margin"]
        bar_w = self.win.winfo_reqwidth()
        screen_w = self.win.winfo_screenwidth()

        pos = cfg["position"]
        if "right" in pos:
            x = screen_w - bar_w - m
        elif "left" in pos:
            x = m
        else:
            x = (screen_w - bar_w) // 2

        if "top" in pos:
            y = m
        else:
            # Just above the tag bar (or overlay if no tag bar)
            if self.overlay.tag_bar:
                ref_y = self.overlay.tag_bar.win.winfo_y()
            else:
                ref_y = self.overlay.root.winfo_y()
            y = max(m, ref_y - 30)

        self.win.geometry(f"+{x}+{y}")

    def _toggle(self):
        self.overlay.toggle_visibility()
        if self.overlay.visible:
            self._toggle_btn.config(text="Hide")
        else:
            self._toggle_btn.config(text="Show")

    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event):
        x = self.win.winfo_x() + (event.x - self._drag_data["x"])
        y = self.win.winfo_y() + (event.y - self._drag_data["y"])
        self.win.geometry(f"+{x}+{y}")


# --- System Tray Icon ---

class TrayIcon:
    """System tray icon with menu for controlling the overlay."""

    def __init__(self, overlay):
        self.overlay = overlay
        self.icon = None
        self._thread = None

    def start(self):
        if not HAS_TRAY:
            return

        image = self._create_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide", self._toggle),
            pystray.MenuItem("Open Config", self._open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self.icon = pystray.Icon("log_overlay", image, "Log Overlay", menu)
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    def _create_icon(self):
        """Create a simple icon image."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Dark blue rounded square with a lighter accent
        draw.rounded_rectangle([4, 4, 60, 60], radius=10, fill="#1a1a2e")
        draw.rounded_rectangle([8, 8, 56, 56], radius=8, outline="#e0e0e0", width=2)
        # Three horizontal lines representing log text
        for y_pos in [22, 32, 42]:
            draw.line([16, y_pos, 48, y_pos], fill="#e0e0e0", width=2)
        return img

    def _toggle(self, icon, item):
        self.overlay.toggle_visibility()

    def _open_config(self, icon, item):
        config_path = os.path.join(get_app_dir(), "config.ini")
        if os.path.isfile(config_path):
            subprocess.Popen(["notepad.exe", config_path])
        else:
            print(f"Config file not found: {config_path}")

    def _quit(self, icon, item):
        self.stop()
        self.overlay.quit()


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Real-time log overlay for Windows (designed for X-Plane)"
    )
    parser.add_argument(
        "--logfile", "-l",
        default=None,
        help="Path to the log file to monitor"
    )
    parser.add_argument(
        "--lines", "-n",
        type=int,
        default=None,
        help="Number of lines to display (default: 15)"
    )
    parser.add_argument(
        "--opacity", "-o",
        type=float,
        default=None,
        help="Window opacity 0.0-1.0 (default: 0.80)"
    )
    parser.add_argument(
        "--font-size", "-f",
        type=int,
        default=None,
        dest="font_size",
        help="Font size in points (default: 11)"
    )
    parser.add_argument(
        "--position", "-p",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        default=None,
        help="Screen position (default: bottom-right)"
    )

    args = parser.parse_args()
    config = load_config(args)

    if not config["logfile"]:
        print("ERROR: No log file specified.")
        print("")
        print("Options:")
        print("  1. Edit config.ini and set the log path")
        print("  2. Run with: python log_overlay.py --logfile \"C:\\X-Plane 12\\Log.txt\"")
        print("")
        print("Could not auto-detect X-Plane installation.")
        sys.exit(1)

    logpath = os.path.abspath(config["logfile"])
    print("Log Overlay")
    print(f"  File:     {logpath}")
    print(f"  Lines:    {config['lines']}")
    print(f"  Position: {config['position']}")
    print(f"  Opacity:  {config['opacity']}")
    print(f"  Colors:   {'on' if config['color_coding'] else 'off'}")
    if HAS_TRAY:
        print(f"  Tray:     enabled")
    print()

    overlay = OverlayWindow(config)
    tailer = LogTailer(
        filepath=logpath,
        max_lines=config["lines"],
        callback=overlay.update_text,
    )
    overlay.tailer = tailer
    tag_bar = TagBar(overlay)
    overlay.tag_bar = tag_bar
    control_bar = ControlBar(overlay)

    status = f"  {os.path.basename(logpath)}"
    overlay.set_status(status)

    tray = TrayIcon(overlay)
    tray.start()
    tailer.start()

    try:
        overlay.run()
    finally:
        tailer.stop()
        tray.stop()


if __name__ == "__main__":
    main()
