"""
QuickLaunch - Fast file/folder navigator with index-based selection
Works on Windows. Run with: python launcher.py
"""

import os
import sys
import json
import subprocess
import platform
import shutil
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".quicklaunch_config.json"
SYNC_FILE   = Path.home() / ".quicklaunch_sync"
PAGE_SIZE   = 5

DEFAULT_CONFIG = {
    "snippets": {
        "~":         str(Path.home()),
        "docs":      str(Path.home() / "Documents"),
        "desktop":   str(Path.home() / "Desktop"),
        "downloads": str(Path.home() / "Downloads"),
    }
}

# ── Platform setup ───────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import msvcrt
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
else:
    import tty
    import termios

# ── ANSI colors ──────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
RED     = "\033[91m"
WHITE   = "\033[97m"
GRAY    = "\033[90m"

# ── Terminal helpers ──────────────────────────────────────────────────────────

def clear():
    os.system("cls" if IS_WINDOWS else "clear")

def home_cursor():
    """Move cursor to top-left without clearing — avoids flash."""
    print("\033[2J\033[H", end="")

def getch():
    """Read a single keypress without Enter."""
    if IS_WINDOWS:
        ch = msvcrt.getwch()
        if ch in ('\x00', '\xe0'):
            ch2 = msvcrt.getwch()
            return '\x00' + ch2
        return ch
    else:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(2)
                return ch + ch2
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ── Config I/O ───────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ── Sync (for 'ql' in PowerShell) ────────────────────────────────────────────

def sync_path(path: Path):
    """Write current path to sync file so PowerShell 'ql' can pick it up."""
    try:
        SYNC_FILE.write_text(str(path), encoding="utf-8")
    except Exception:
        pass

# ── PowerShell helpers ────────────────────────────────────────────────────────

def _ps_escape(path: Path) -> str:
    """Escape path for PowerShell single-quoted strings."""
    return str(path).strip().replace("'", "''")

def _find_powershell() -> str:
    candidates = [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "powershell.exe"

def open_terminal(path: Path):
    """Open PowerShell at the given directory."""
    p = _ps_escape(path)
    ps_exe = _find_powershell()
    cmd = f'"{ps_exe}" -NoExit -Command "Set-Location \'{p}\'"'
    if IS_WINDOWS:
        try:
            subprocess.Popen(f'wt -p "Windows PowerShell" -- {cmd}', shell=True)
        except Exception:
            subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", "-a", "Terminal", str(path)])
    else:
        for term in ["gnome-terminal", "xterm", "konsole"]:
            if shutil.which(term):
                subprocess.Popen([term, "--working-directory", str(path)])
                break

# ── File helpers ──────────────────────────────────────────────────────────────

def list_entries(directory: Path):
    try:
        entries = list(directory.iterdir())
    except PermissionError:
        return []
    dirs  = sorted([e for e in entries if e.is_dir()],  key=lambda e: e.name.lower())
    files = sorted([e for e in entries if e.is_file()], key=lambda e: e.name.lower())
    return [(e.name, e, e.is_dir()) for e in dirs + files]

def open_path(path: Path):
    p = str(path)
    if IS_WINDOWS:
        os.startfile(p)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])

def resolve_input(text: str, config: dict, relative_to: Path) -> Path | None:
    """Resolve typed text: snippet[/sub], /sub (inside relative_to), relative or absolute path."""
    text = text.strip()
    if not text:
        return None
    snippets = config.get("snippets", {})
    parts = text.replace("\\", "/").split("/")
    first = parts[0].lower()
    if first in snippets:
        base = Path(snippets[first])
        rest = "/".join(parts[1:])
        path = base / rest if rest else base
    elif text[0] in "/\\":
        # A leading slash means "inside the folder you're in", e.g. after a snippet jump
        path = relative_to / text.lstrip("/\\")
    else:
        path = Path(text.replace("\\", os.sep)).expanduser()
        if not path.is_absolute():
            path = relative_to / path
    return path if path.exists() else None

# ── File operations ───────────────────────────────────────────────────────────

def rename_entry(path: Path, new_name: str) -> str:
    try:
        path.rename(path.parent / new_name)
        return f"Renamed '{path.name}' → '{new_name}'"
    except FileExistsError:
        return f"Error: '{new_name}' already exists"
    except Exception as e:
        return f"Error: {e}"

def create_entry(current_path: Path, entry_type: str, name: str) -> tuple[str, Path | None]:
    """Returns (status_message, created_path_or_None)."""
    try:
        target = current_path / name
        if entry_type == "folder":
            target.mkdir(parents=True, exist_ok=False)
            return f"Created folder: '{name}'", target
        elif entry_type == "file":
            target.touch(exist_ok=False)
            return f"Created file: '{name}'", target
        else:
            return "Usage: :create file/folder [name]", None
    except FileExistsError:
        return f"Error: '{name}' already exists", None
    except Exception as e:
        return f"Error: {e}", None

def duplicate_entry(path: Path, new_name: str) -> str:
    try:
        target = path.parent / new_name
        if path.is_dir():
            shutil.copytree(str(path), str(target))
        else:
            shutil.copy2(str(path), str(target))
        return f"Duplicated '{path.name}' → '{new_name}'"
    except FileExistsError:
        return f"Error: '{new_name}' already exists"
    except Exception as e:
        return f"Error: {e}"

def _recycle(path: Path) -> bool:
    """Move a file or folder to the Windows Recycle Bin (SHFileOperationW)."""
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    # ALLOWUNDO (Recycle Bin) | NOCONFIRMATION | SILENT | NOERRORUI, plus WANTNUKEWARNING
    # so Windows still warns if it would have to delete permanently (e.g. too big for the bin)
    flags = 0x0040 | 0x0010 | 0x0004 | 0x0400 | 0x4000
    op = SHFILEOPSTRUCTW(wFunc=FO_DELETE, pFrom=str(path.resolve()) + "\0", fFlags=flags)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return result == 0 and not op.fAnyOperationsAborted and not path.exists()

def delete_entry(path: Path) -> str:
    """Recycle on Windows; elsewhere delete permanently."""
    try:
        if IS_WINDOWS:
            if _recycle(path):
                return f"Moved to Recycle Bin: '{path.name}'"
            return f"Error: could not move '{path.name}' to the Recycle Bin"
        if path.is_dir():
            shutil.rmtree(str(path))
        else:
            path.unlink()
        return f"Deleted: '{path.name}'"
    except Exception as e:
        return f"Error: {e}"

def _unused_target(dest_dir: Path, src: Path) -> Path:
    """dest_dir/name, or name_copy, name_copy2, ... if that is already taken."""
    target = dest_dir / src.name
    n = 1
    while target.exists():
        suffix = "_copy" if n == 1 else f"_copy{n}"
        target = dest_dir / f"{src.stem}{suffix}{src.suffix}"
        n += 1
    return target

def paste_entry(src: Path, dest_dir: Path) -> str:
    try:
        target = _unused_target(dest_dir, src)
        if src.is_dir():
            shutil.copytree(str(src), str(target))
        else:
            shutil.copy2(str(src), str(target))
        return f"Pasted: '{target.name}'"
    except Exception as e:
        return f"Error: {e}"

def move_entry(src: Path, dest_dir: Path) -> str:
    try:
        target = _unused_target(dest_dir, src)
        shutil.move(str(src), str(target))
        return f"Moved: '{target.name}'"
    except Exception as e:
        return f"Error: {e}"

# ── UI ────────────────────────────────────────────────────────────────────────

LOGO = f"""{CYAN}{BOLD}
  ╔═══════════════════════════════════╗
  ║  ⚡ QuickLaunch  File Navigator   ║
  ╚═══════════════════════════════════╝{RESET}"""

HELP = (
    f"{GRAY}  [1-5] open  │  [←][→] pages  │  [↑] go up  │  "
    f"[@] snippets  │  [Tab] autocomplete  │  [:help] commands  │  [Esc] quit{RESET}"
)

def icon(is_dir: bool, name: str) -> str:
    if is_dir:
        return "📁"
    ext = Path(name).suffix.lower()
    return {
        ".pdf":"📄",".doc":"📝",".docx":"📝",".txt":"📝",
        ".xls":"📊",".xlsx":"📊",".csv":"📊",
        ".jpg":"🖼️",".jpeg":"🖼️",".png":"🖼️",".gif":"🖼️",
        ".mp4":"🎬",".mov":"🎬",".avi":"🎬",
        ".mp3":"🎵",".wav":"🎵",".flac":"🎵",
        ".zip":"📦",".rar":"📦",".7z":"📦",
        ".py":"🐍",".js":"📜",".ts":"📜",
        ".exe":"⚙️",".bat":"⚙️",".sh":"⚙️",
    }.get(ext, "📄")

def render(current_path, entries, page, query, status, config, clipboard_name="", cut_name=""):
    home_cursor()
    print(LOGO)
    print()

    # Clipboard indicator
    if cut_name:
        print(f"  {YELLOW}✂ Cut: {cut_name}{RESET}")
        print()
    elif clipboard_name:
        print(f"  {CYAN}📋 Copied: {clipboard_name}{RESET}")
        print()

    # Current path
    print(f"  {GRAY}📍 {CYAN}{BOLD}{current_path}{RESET}")
    print(f"  {GRAY}{'─' * 50}{RESET}")

    total = len(entries)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start = page * PAGE_SIZE
    visible = entries[start : start + PAGE_SIZE]

    if not visible:
        print(f"\n  {GRAY}(empty directory){RESET}\n")
    else:
        for i, (name, path, is_dir) in enumerate(visible, 1):
            idx_str  = f"{YELLOW}{BOLD}[{i}]{RESET}"
            ic       = icon(is_dir, name)
            name_col = f"{BOLD}{WHITE}{name}{RESET}" if is_dir else f"{WHITE}{name}{RESET}"
            type_tag = f"{BLUE} DIR{RESET}" if is_dir else f"{GRAY} file{RESET}"
            print(f"  {idx_str}  {ic}  {name_col}{type_tag}")

    # Pad to fixed height so leftover lines don't bleed through
    rendered_items = len(visible) if visible else 1
    for _ in range(PAGE_SIZE - rendered_items):
        print()

    print()
    print(f"  {GRAY}Page {page+1}/{total_pages}  ({total} items total){RESET}")
    print(f"  {GRAY}←/→ to change page,  ↑ to go up{RESET}")
    print()
    print(HELP)
    print()

    if status:
        print(f"  {GREEN}✔ {status:<60}{RESET}")
    else:
        print(f"  {' ' * 62}")
    print()

    print(f"  {CYAN}>{RESET} {BOLD}{query}{RESET}\033[K", end="", flush=True)

def render_snippets_editor(config: dict):
    clear()
    print(LOGO)
    print(f"\n  {YELLOW}{BOLD}── Snippet Manager ──{RESET}\n")
    snips = config.get("snippets", {})
    if snips:
        for i, (k, v) in enumerate(snips.items(), 1):
            print(f"  {YELLOW}[{i}]{RESET}  {MAGENTA}{BOLD}{k:<12}{RESET}  →  {GRAY}{v}{RESET}")
    else:
        print(f"  {GRAY}(no snippets yet){RESET}")
    print(f"\n  {GRAY}[a] add  [d] delete  [b] back{RESET}\n")
    print(f"  {CYAN}>{RESET} ", end="", flush=True)

def show_help(getch_fn):
    clear()
    print(LOGO)
    print(f"\n  {YELLOW}{BOLD}── Command Guide ──{RESET}\n")
    commands = [
        (":terminal",                    "Open PowerShell at current folder"),
        (":search [name]",               "Search folders by name (depth 5)"),
        (":rename [1-5] [new name]",     "Rename a file or folder"),
        (":create file/folder [name]",   "Create without opening"),
        (":createop file/folder [name]", "Create then open/enter immediately"),
        (":duplicate [1-5] [new name]",  "Duplicate a file or folder"),
        (":delete [1-5]",                "Move to Recycle Bin (asks y/N first)"),
        (":copy [1-5]",                  "Copy to clipboard"),
        (":cut [1-5]",                   "Cut — use :paste to move"),
        (":paste",                       "Paste clipboard into current folder"),
        (":snippet [name]",              "Save current path as snippet"),
        (":help",                        "Show this guide"),
        ("",                             ""),
        ("Tab",                          "Autocomplete snippet name"),
        ("@",                            "Open snippet manager"),
        ("ql  (in PowerShell)",          "Jump PowerShell to QuickLaunch location"),
    ]
    for cmd, desc in commands:
        if cmd == "":
            print()
        else:
            print(f"  {CYAN}{BOLD}{cmd:<35}{RESET}  {GRAY}{desc}{RESET}")
    print(f"\n  {GRAY}Press any key to continue...{RESET}")
    getch_fn()

# ── Snippet editor ────────────────────────────────────────────────────────────

def run_snippets_editor(config: dict):
    while True:
        render_snippets_editor(config)
        line = input().strip()
        if line.lower() in ("b", "back", ""):
            break
        elif line.lower().startswith("a"):
            print(f"\n  {CYAN}Snippet key:{RESET} ", end="")
            key = input().strip()
            print(f"  {CYAN}Path:{RESET} ", end="")
            val = input().strip()
            if key and val:
                config["snippets"][key.lower()] = val
                save_config(config)
        elif line.lower().startswith("d"):
            keys = list(config.get("snippets", {}).keys())
            print(f"  {CYAN}Number to delete:{RESET} ", end="")
            try:
                n = int(input().strip()) - 1
                if 0 <= n < len(keys):
                    del config["snippets"][keys[n]]
                    save_config(config)
            except ValueError:
                pass

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    config       = load_config()
    # 'ql' passes the shell's current folder; otherwise start at home
    start        = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home()
    current_path = start if start.is_dir() else Path.home()
    entries      = list_entries(current_path)
    page         = 0
    query        = ""
    status       = ""
    clipboard    = None   # Path for :copy
    cut_clip     = None   # Path for :cut
    pending_del  = None   # Path waiting for y/N after :delete
    query_base   = current_path  # folder typed relative paths start from
    needs_render = True

    # Write initial path for 'ql'
    sync_path(current_path)

    while True:
        if needs_render:
            render(
                current_path, entries, page, query, status, config,
                clipboard_name=clipboard.name if clipboard else "",
                cut_name=cut_clip.name if cut_clip else "",
            )
            status = ""
            needs_render = False

        ch = getch()

        # ── Delete confirmation (any key other than y cancels, including Esc) ─
        if pending_del is not None:
            if ch in ('y', 'Y'):
                status = delete_entry(pending_del)
                entries = list_entries(current_path)
            else:
                status = "Delete cancelled"
            pending_del = None
            needs_render = True
            continue

        # ── Quit ────────────────────────────────────────────────────────────
        if ch == '\x1b':
            clear()
            print(f"\n  {CYAN}👋 Bye!{RESET}\n")
            break

        total_pages = max(1, (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE)

        # ── Arrow keys ───────────────────────────────────────────────────────
        if ch in ('\x00M', '\x1b[C'):           # right → next page
            if page < total_pages - 1:
                page += 1
            needs_render = True
            continue

        if ch in ('\x00K', '\x1b[D'):           # left → prev page
            if page > 0:
                page -= 1
            needs_render = True
            continue

        if ch in ('\x00H', '\x1b[A'):           # up → parent folder
            parent = current_path.parent
            if parent != current_path:
                current_path = parent
                entries = list_entries(current_path)
                page = 0
                query = ""
                sync_path(current_path)
            needs_render = True
            continue

        # ── Snippet manager ──────────────────────────────────────────────────
        if ch == '@':
            run_snippets_editor(config)
            config = load_config()
            needs_render = True
            continue

        # ── Tab autocomplete ─────────────────────────────────────────────────
        if ch == '\t':
            if query and not query.startswith(':'):
                snippets = config.get("snippets", {})
                matches = [k for k in snippets if k.startswith(query.lower())]
                if len(matches) == 1:
                    query = matches[0]
                elif len(matches) > 1:
                    if query.lower() in matches:
                        query = matches[(matches.index(query.lower()) + 1) % len(matches)]
                    else:
                        query = matches[0]
            needs_render = True
            continue

        # ── Number selection (only before typing, so paths like 2026_I4 can be typed) ─
        if ch.isdigit() and ch != '0' and not query:
            idx = int(ch) - 1
            visible = entries[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
            if idx < len(visible):
                name, path, is_dir = visible[idx]
                if is_dir:
                    current_path = path
                    entries = list_entries(current_path)
                    page = 0
                    query = ""
                    status = f"Opened folder: {name}"
                    sync_path(current_path)
                else:
                    try:
                        open_path(path)
                        status = f"Opened: {name}"
                    except Exception as e:
                        status = f"Error: {e}"
            needs_render = True
            continue

        # ── Backspace ────────────────────────────────────────────────────────
        if ch in ('\x08', '\x7f'):
            if query:
                query = query[:-1]
                if not query.startswith(':'):
                    resolved = resolve_input(query, config, query_base)
                    if resolved and resolved.is_dir():
                        current_path = resolved
                        entries = list_entries(current_path)
                        page = 0
                        sync_path(current_path)
            needs_render = True
            continue

        # ── Enter — all commands ─────────────────────────────────────────────
        if ch in ('\r', '\n'):
            q = query.strip().lower()

            # :terminal
            if q == ':terminal':
                try:
                    open_terminal(current_path)
                    status = f"Opened terminal at: {current_path.name}"
                except Exception as e:
                    status = f"Error: {e}"
                query = ""
                needs_render = True
                continue

            # :search [name]
            if query.startswith(':search '):
                term = query[8:].strip()
                if term:
                    matches = []
                    try:
                        for root, dirs, _ in os.walk(current_path):
                            depth = len(Path(root).parts) - len(current_path.parts)
                            if depth >= 5:
                                dirs.clear()
                                continue
                            for d in dirs:
                                if term.lower() in d.lower():
                                    matches.append(Path(root) / d)
                            if len(matches) >= 50:
                                break
                    except PermissionError:
                        pass
                    if matches:
                        entries = [(str(p.relative_to(current_path)), p, True) for p in matches]
                        status = f"Found {len(matches)} result(s) for '{term}'"
                    else:
                        status = f"No folders found for '{term}'"
                query = ""
                needs_render = True
                continue

            # :rename [idx] [name]
            if query.startswith(':rename '):
                parts = query[8:].strip().split(' ', 1)
                if len(parts) == 2 and parts[0].isdigit():
                    idx = int(parts[0]) - 1
                    visible = entries[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
                    if 0 <= idx < len(visible):
                        _, path, _ = visible[idx]
                        status = rename_entry(path, parts[1].strip())
                        entries = list_entries(current_path)
                    else:
                        status = "Error: invalid index"
                else:
                    status = "Usage: :rename [1-5] new_name"
                query = ""
                needs_render = True
                continue

            # :create file/folder [name]
            if query.startswith(':create '):
                parts = query[8:].strip().split(' ', 1)
                if len(parts) == 2:
                    status, _ = create_entry(current_path, parts[0].strip().lower(), parts[1].strip())
                    entries = list_entries(current_path)
                else:
                    status = "Usage: :create file/folder [name]"
                query = ""
                needs_render = True
                continue

            # :createop file/folder [name] → create then open/enter
            if query.startswith(':createop '):
                parts = query[10:].strip().split(' ', 1)
                if len(parts) == 2:
                    entry_type = parts[0].strip().lower()
                    name = parts[1].strip()
                    status, created = create_entry(current_path, entry_type, name)
                    if created:
                        if entry_type == "folder":
                            current_path = created
                            entries = list_entries(current_path)
                            page = 0
                            sync_path(current_path)
                        else:
                            entries = list_entries(current_path)
                            try:
                                open_path(created)
                            except Exception as e:
                                status = f"Created but failed to open: {e}"
                else:
                    status = "Usage: :createop file/folder [name]"
                query = ""
                needs_render = True
                continue

            # :duplicate [idx] [name]
            if query.startswith(':duplicate '):
                parts = query[11:].strip().split(' ', 1)
                if len(parts) == 2 and parts[0].isdigit():
                    idx = int(parts[0]) - 1
                    visible = entries[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
                    if 0 <= idx < len(visible):
                        _, path, _ = visible[idx]
                        status = duplicate_entry(path, parts[1].strip())
                        entries = list_entries(current_path)
                    else:
                        status = "Error: invalid index"
                else:
                    status = "Usage: :duplicate [1-5] new_name"
                query = ""
                needs_render = True
                continue

            # :delete [idx]
            if query.startswith(':delete '):
                parts = query[8:].strip()
                if parts.isdigit():
                    idx = int(parts) - 1
                    visible = entries[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
                    if 0 <= idx < len(visible):
                        _, path, _ = visible[idx]
                        pending_del = path
                        where = "move it to the Recycle Bin" if IS_WINDOWS else "delete it permanently"
                        status = f"Delete '{path.name}'? Press y to {where}, any other key to cancel"
                    else:
                        status = "Error: invalid index"
                else:
                    status = "Usage: :delete [1-5]"
                query = ""
                needs_render = True
                continue

            # :copy [idx]
            if query.startswith(':copy '):
                parts = query[6:].strip()
                if parts.isdigit():
                    idx = int(parts) - 1
                    visible = entries[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
                    if 0 <= idx < len(visible):
                        _, path, _ = visible[idx]
                        clipboard = path
                        cut_clip  = None
                        status = f"Copied: '{path.name}'"
                    else:
                        status = "Error: invalid index"
                else:
                    status = "Usage: :copy [1-5]"
                query = ""
                needs_render = True
                continue

            # :cut [idx]
            if query.startswith(':cut '):
                parts = query[5:].strip()
                if parts.isdigit():
                    idx = int(parts) - 1
                    visible = entries[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
                    if 0 <= idx < len(visible):
                        _, path, _ = visible[idx]
                        cut_clip  = path
                        clipboard = None
                        status = f"Cut: '{path.name}' — navigate then :paste"
                    else:
                        status = "Error: invalid index"
                else:
                    status = "Usage: :cut [1-5]"
                query = ""
                needs_render = True
                continue

            # :paste
            if q == ':paste':
                if cut_clip:
                    status = move_entry(cut_clip, current_path)
                    if not status.startswith("Error"):
                        cut_clip = None
                    entries = list_entries(current_path)
                elif clipboard:
                    status = paste_entry(clipboard, current_path)
                    entries = list_entries(current_path)
                else:
                    status = "Nothing to paste — use :copy or :cut first"
                query = ""
                needs_render = True
                continue

            # :snippet [name]
            if query.startswith(':snippet '):
                name = query[9:].strip().lower()
                if name:
                    config["snippets"][name] = str(current_path)
                    save_config(config)
                    status = f"Snippet '{name}' → '{current_path}'"
                else:
                    status = "Usage: :snippet [name]"
                query = ""
                needs_render = True
                continue

            # :help
            if q == ':help':
                show_help(getch)
                query = ""
                needs_render = True
                continue

            # plain path / snippet navigation
            if query:
                snippets = config.get("snippets", {})
                if query.lower() in snippets:
                    target = Path(snippets[query.lower()])
                    current_path = target
                    entries = list_entries(current_path)
                    page = 0
                    query = ""
                    status = f"Opened folder: {target.name}"
                    sync_path(current_path)
                else:
                    resolved = resolve_input(query, config, query_base)
                    if resolved:
                        if resolved.is_dir():
                            current_path = resolved
                            entries = list_entries(current_path)
                            page = 0
                            query = ""
                            status = f"Navigated to: {current_path.name or str(current_path)}"
                            sync_path(current_path)
                        else:
                            try:
                                open_path(resolved)
                                status = f"Opened: {resolved.name}"
                                query = ""
                            except Exception as e:
                                status = f"Error: {e}"
                    else:
                        status = f"Path not found: {query}"
            needs_render = True
            continue

        # ── Printable character ───────────────────────────────────────────────
        if ch.isprintable() and len(ch) == 1:
            if not query:
                query_base = current_path
            query += ch
            if not query.startswith(':'):
                snippets = config.get("snippets", {})
                key = query.lower()
                # Jump as soon as the name is complete, unless a longer snippet starts the same way
                if key in snippets and not any(k != key and k.startswith(key) for k in snippets):
                    target = Path(snippets[key])
                    current_path = target
                    entries = list_entries(current_path)
                    page = 0
                    query = ""
                    status = f"Opened folder: {target.name}"
                    sync_path(current_path)
                else:
                    resolved = resolve_input(query, config, query_base)
                    if resolved and resolved.is_dir():
                        current_path = resolved
                        entries = list_entries(current_path)
                        page = 0
                        sync_path(current_path)
            needs_render = True
            continue

if __name__ == "__main__":
    main()