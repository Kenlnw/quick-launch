# QuickLaunch — File Navigator

A keyboard-driven file launcher for Windows. No mouse, no typing Japanese folder names — just index numbers and short snippets.

## Requirements

- Python 3.10+ (https://python.org)
- `launcher.py` uses only Python's standard library
- The optional hotkey tray (`hotkey_tray.py`) needs: `pip install keyboard pystray pillow`

## How to Run

| Way | What it does |
|-----|--------------|
| `ql` (in PowerShell) | Opens QuickLaunch in your current folder; when you quit, your terminal moves to wherever you ended up |
| `python launcher.py` | Starts in your home folder |
| `python launcher.py C:\some\folder` | Starts in that folder (falls back to home if it doesn't exist) |
| Double-click `run.bat` | Same as `python launcher.py` |
| **Ctrl+Alt+Space** | Opens QuickLaunch in a new terminal — only while `hotkey_tray.py` is running (see below) |

---

## Controls

| Key | Action |
|-----|--------|
| `1` – `5` | Open that file or enter that folder (when nothing is typed yet) |
| `→` / `←` | Next / previous page (5 items per page) |
| `↑` | Go up to the parent folder |
| `@` | Open the Snippet Manager |
| `Tab` | Autocomplete a snippet name (press again to cycle through matches) |
| Type text | Live-navigate as you type (see below) |
| `Enter` | Confirm the typed path, or run a `:command` |
| `Backspace` | Delete the last typed character |
| `Esc` | Quit |

Letters you type always go into the input box, so keys like `q` or `a` don't do anything on their own.

### Typing paths and snippets

QuickLaunch navigates live as you type. Press `Enter` to finish, then the number keys select again.

- **Names in the current folder:** type a folder's name, e.g. `Denshi_I4`. Relative names are looked up from the folder you were in when you started typing.
- **Full paths:** e.g. `C:\Users\you\Documents`. Typing a file's path and pressing `Enter` opens the file.
- **Snippets** jump the moment you finish typing the name — no `Enter` needed. Type `notes` and you're in your Notes folder.
  - If another snippet starts with the same letters (e.g. `pro` and `projects`), the shorter one waits for `Enter` so you can keep typing the longer one.
- **Snippet + subfolder:** keep typing after the snippet with a `/`, e.g. `school/2026_I4`. A leading `/` always means "inside the folder you're in".
- **Digits:** with nothing typed, `1`–`5` select an item. Digits later in a name (`i4`, `school/2026_I4`) are typed normally. For a name that *starts* with a digit, type a `/` first: `/2026_I4`.
- `Tab` completes a partly typed snippet name, e.g. `sch` → `school`.

---

## Commands

Type these and press `Enter`. `[1-5]` means the item number shown on the current page.

| Command | Action |
|---------|--------|
| `:terminal` | Open PowerShell at the current folder |
| `:search [name]` | Find folders whose name contains `name` (up to 5 levels deep, 50 results) |
| `:rename [1-5] [new name]` | Rename a file or folder |
| `:create file/folder [name]` | Create a file or folder without opening it |
| `:createop file/folder [name]` | Create, then open the file / enter the folder |
| `:duplicate [1-5] [new name]` | Make a copy next to the original |
| `:delete [1-5]` | Move a file or folder to the Recycle Bin — asks first; press `y` to confirm, any other key cancels |
| `:copy [1-5]` | Copy an item to QuickLaunch's clipboard |
| `:cut [1-5]` | Mark an item to move — then navigate and `:paste` |
| `:paste` | Paste the copied item, or move the cut item, into the current folder (never overwrites: adds `_copy`, `_copy2`, … if the name is taken) |
| `:snippet [name]` | Save the current folder as a snippet |
| `:help` | Show the command guide |

---

## Snippets

Snippets are short aliases for your frequently-used folders. Instead of typing:
```
C:\Users\YourName\Projects\MyJapaneseFolder
```
You type:
```
projects
```
And it jumps right there.

### Default Snippets
Used only when you have no config file yet:

| Snippet | Points to |
|---------|-----------|
| `~` | Your home folder |
| `docs` | `~\Documents` |
| `desktop` | `~\Desktop` |
| `downloads` | `~\Downloads` |

Once `~/.quicklaunch_config.json` exists, its `snippets` list **replaces** these defaults completely. If your Documents or Desktop live in OneDrive, point `docs` / `desktop` there in the config.

### Adding Your Own
- In QuickLaunch: go to the folder and type `:snippet name`, or press `@` → `a`
- Or edit `~/.quicklaunch_config.json` directly:

```json
{
  "snippets": {
    "school": "C:\\Users\\YourName\\School",
    "notes": "C:\\Users\\YourName\\Notes"
  }
}
```

Save the file as UTF-8 **without a BOM** — if the file can't be read, QuickLaunch silently falls back to the defaults.

Give snippets different first letters where you can, so a single letter + `Tab` gets you there.

---

## `ql` — move your PowerShell to where you browsed

`ql` is a PowerShell function (in your `$PROFILE`). It:

1. Starts `launcher.py` in your current folder
2. Waits until you press `Esc`
3. Moves the terminal to the last folder you were in

QuickLaunch records that folder in `~/.quicklaunch_sync` every time you change folders. If you quit without moving, you stay where you were.

```powershell
function ql {
    $sync = "$env:USERPROFILE\.quicklaunch_sync"
    $before = (Get-Item -LiteralPath $sync -ErrorAction SilentlyContinue).LastWriteTimeUtc
    python "$env:USERPROFILE\Projects\tools\QuickLaunch\launcher.py" (Get-Location -PSProvider FileSystem).ProviderPath

    # Only move if the launcher actually ran and recorded a folder this time
    $after = Get-Item -LiteralPath $sync -ErrorAction SilentlyContinue
    if ($after -and $after.LastWriteTimeUtc -ne $before) {
        $target = (Get-Content -LiteralPath $sync -Raw -Encoding utf8).Trim()
        if (Test-Path -LiteralPath $target -PathType Container) { Set-Location -LiteralPath $target }
    }
}
```

---

## Hotkey Tray (optional)

`hotkey_tray.py` sits in the system tray and opens QuickLaunch in a new Windows Terminal window when you press **Ctrl+Alt+Space** from anywhere.

```
pip install keyboard pystray pillow
python hotkey_tray.py
```

- Change the hotkey by editing `HOTKEY` near the top of `hotkey_tray.py`
- Quit from the tray icon's right-click menu
- To start it with Windows, put a shortcut in your Startup folder, or use a `.vbs` that runs `pythonw hotkey_tray.py` without a console window

Windows opened from the hotkey start in your home folder and don't move an existing terminal. Use `ql` for that.

---

## Example Workflow

You want to open a file deep inside a Japanese-named folder:

1. Type `projects` → jumps to your Projects folder instantly
2. See 5 items listed. Your target folder is `[3]` → press `3`
3. Now inside that subfolder. File you want is `[2]` → press `2`
4. File opens. Done. **Zero Japanese typing.**

---

## Files

| File | Purpose |
|------|---------|
| `~/.quicklaunch_config.json` | Your snippets |
| `~/.quicklaunch_sync` | Last folder visited (read by `ql`) |

## Tips

- Folders always appear **before** files in the list
- Use `→` / `←` to page through folders with many items
- Deleted something by mistake? Restore it from the Recycle Bin. (If an item is too big for the Recycle Bin, Windows warns you before deleting it permanently.)
