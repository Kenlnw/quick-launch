"""
QuickLaunch Tray — runs in the background, listens for a global hotkey.
Press Ctrl+Space (default) anywhere to pop open a new terminal with launcher.py.

Install deps first:
    pip install keyboard pystray pillow

Run:
    python hotkey_tray.py
    (minimize to tray, then use the hotkey anytime)
"""

import sys
import os
import subprocess
import threading
from pathlib import Path

try:
    import keyboard
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Missing dependencies. Run:")
    print("    pip install keyboard pystray pillow")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────

# Change this to any hotkey combo you like, e.g.:
#   "ctrl+space", "alt+q", "ctrl+shift+f", "f9"
HOTKEY = "ctrl+alt+space"

# Path to your launcher.py
LAUNCHER = Path(__file__).parent / "launcher.py"

# ── Launch logic ─────────────────────────────────────────────────────────────

def launch():
    """Open a new Windows Terminal / CMD window running launcher.py."""
    python = sys.executable

    # Try Windows Terminal first, fall back to plain cmd
    try:
        subprocess.Popen(
            ["wt", "python", str(LAUNCHER)],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except FileNotFoundError:
        subprocess.Popen(
            ["cmd", "/c", "start", "cmd", "/k", python, str(LAUNCHER)],
            shell=True
        )

def on_hotkey():
    # Run in a thread so the hotkey listener doesn't block
    threading.Thread(target=launch, daemon=True).start()

# ── Tray icon ─────────────────────────────────────────────────────────────────

def make_icon():
    """Draw a simple lightning bolt icon for the tray."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Dark circle background
    d.ellipse([2, 2, 62, 62], fill=(30, 30, 40, 255))
    # Yellow lightning bolt
    bolt = [(38, 4), (20, 34), (32, 34), (26, 60), (46, 28), (34, 28), (38, 4)]
    d.polygon(bolt, fill=(255, 210, 50, 255))
    return img

def on_quit(icon, item):
    icon.stop()
    keyboard.unhook_all()
    os.kill(os.getpid(), 9)

def run_tray():
    icon = pystray.Icon(
        name="QuickLaunch",
        icon=make_icon(),
        title=f"QuickLaunch  [{HOTKEY.upper()}]",
        menu=pystray.Menu(
            pystray.MenuItem(f"Open Launcher  ({HOTKEY.upper()})", lambda i, it: on_hotkey()),
            pystray.MenuItem("Change hotkey → edit HOTKEY in hotkey_tray.py", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        )
    )
    icon.run()

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"⚡ QuickLaunch tray running.")
    print(f"   Hotkey : {HOTKEY.upper()}")
    print(f"   Launcher: {LAUNCHER}")
    print(f"   Minimise this window or let it run in the background.")
    print(f"   Right-click the tray icon to quit.\n")

    keyboard.add_hotkey(HOTKEY, on_hotkey, suppress=False)
    run_tray()
