"""
A small window for entering an E37 account, for people who do not use a terminal.

The point is who sees the password. When Claude (or any assistant) sets e37-cli
up for someone, it runs `e37 account add NAME --dialog`; this window opens on the
person's own screen, they type into it, and the values go straight to the OS
keychain. The assistant gets back "saved" or "cancelled" and nothing else — no
secret passes through the chat, the command line or the process list.

tkinter ships with Python on Windows and with the python.org and Homebrew
builds on macOS. Where it is missing on a Mac, AppleScript dialogs via osascript
do the same job one field at a time.
"""

import subprocess
import sys

from . import E37Error

FIELDS = [
    # key, label, secret
    ("webshopId", "Webbshop-ID", False),
    ("baseUrl", "API-adress", False),
    ("account", "Rapport-konto (slug)", False),
    ("key", "API-nyckel", True),
    ("email", "E-post (inloggning i E37 Admin)", False),
    ("password", "Lösenord (inloggning i E37 Admin)", True),
]


def ask(name, current):
    """Show the form. `current` holds today's values; secrets are never shown,
    only whether one is stored. Returns the new flat values, or None if cancelled."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        if sys.platform == "darwin":
            return _ask_osascript(name, current)
        raise E37Error("Det går inte att visa en dialog här (tkinter saknas). Använd: e37 account add NAMN i en terminal.")
    return _ask_tk(name, current)


def _ask_tk(name, current):
    import tkinter as tk

    result = {}
    root = tk.Tk()
    root.title(f"E37-konto: {name}")
    root.resizable(False, False)
    # Over everything else: the person was just told by a chat that a window
    # would open, and one hidden behind that chat looks like nothing happened.
    root.attributes("-topmost", True)

    frame = tk.Frame(root, padx=16, pady=14)
    frame.pack()
    tk.Label(frame, text=f"Uppgifterna sparas bara i din egen nyckelring på den här datorn.",
             justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    entries = {}
    for i, (key, label, secret) in enumerate(FIELDS, start=1):
        tk.Label(frame, text=label).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=3)
        e = tk.Entry(frame, width=36, show="•" if secret else "")
        e.grid(row=i, column=1, pady=3)
        if not secret and current.get(key):
            e.insert(0, current[key])
        entries[key] = e
    hint = "Lämna ett hemligt fält tomt för att behålla det som redan är sparat." if any(
        current.get(k) for k, _, s in FIELDS if s) else "Alla fält utom webbshop-ID får lämnas tomma."
    tk.Label(frame, text=hint, fg="#555").grid(row=len(FIELDS) + 1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def save(_=None):
        result.update({k: e.get().strip() for k, e in entries.items()})
        root.destroy()

    buttons = tk.Frame(frame)
    buttons.grid(row=len(FIELDS) + 2, column=0, columnspan=2, sticky="e", pady=(12, 0))
    tk.Button(buttons, text="Avbryt", width=10, command=root.destroy).pack(side="right", padx=(6, 0))
    tk.Button(buttons, text="Spara", width=10, command=save, default="active").pack(side="right")
    root.bind("<Return>", save)
    root.bind("<Escape>", lambda _: root.destroy())
    entries["webshopId"].focus_set()
    root.after(200, lambda: root.focus_force())
    root.mainloop()
    return result or None


def _ask_osascript(name, current):
    """macOS without tkinter: one AppleScript dialog per field.

    The default answer and the title travel in argv, so only non-secret values
    are ever put there; a secret field always starts empty.
    """
    out = {}
    for key, label, secret in FIELDS:
        default = "" if secret else (current.get(key) or "")
        script = ('on run argv\n'
                  'display dialog (item 1 of argv) default answer (item 2 of argv) '
                  f'{"with hidden answer " if secret else ""}'
                  'with title (item 3 of argv) buttons {"Avbryt", "Nästa"} default button "Nästa" cancel button "Avbryt"\n'
                  'return text returned of result\nend run')
        r = subprocess.run(["osascript", "-e", script, label, default, f"E37-konto: {name}"],
                           capture_output=True, text=True)
        if r.returncode:
            return None  # cancelled
        out[key] = r.stdout.rstrip("\n").strip()
    return out
