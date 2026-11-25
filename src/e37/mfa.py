"""Ephemeral MFA input, directly from the person, never from chat or argv."""

import getpass
import os
import subprocess
import sys
import warnings

from . import E37Error


def ask_code(account, attempt=1):
    mode = os.environ.get("E37_MFA_MODE", "auto").lower()
    if mode not in ("auto", "terminal", "dialog", "none"):
        raise E37Error("E37_MFA_MODE måste vara auto, terminal, dialog eller none.")
    if mode == "none":
        raise E37Error("E37 kräver MFA. Kör interaktivt eller med E37_MFA_MODE=dialog på din egen dator.")
    message = (f"E37-konto: {account}\nAnge engångskoden från din app eller E37:s e-post."
               if attempt == 1 else
               f"E37-konto: {account}\nKoden godkändes inte. Ange en aktuell kod från appen eller e-posten.")
    if mode == "terminal" or (mode == "auto" and sys.stdin.isatty()):
        try:
            # getpass otherwise falls back to echoing input, unsafe for agents.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                code = getpass.getpass(message + "\nMFA-kod: ")
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
            raise E37Error("MFA avbröts eller säker terminal saknas. Använd E37_MFA_MODE=dialog.") from None
    else:
        print("E37 kräver MFA. Ange koden i fönstret på din dator (inte i chatten).",
              file=sys.stderr, flush=True)
        code = _dialog(message)
    if not code or not code.strip():
        raise E37Error("MFA-inloggningen avbröts. Ingen kod skickades.")
    return code.strip()


def _dialog(message):
    try:
        import tkinter as tk
    except ImportError:
        return _fallback(message)
    try:
        root = tk.Tk()
    except tk.TclError:
        return _fallback(message)
    try:
        root.title("E37 – tvåfaktorsinloggning")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        tk.Label(root, text=message, padx=20, pady=15, justify="left").pack()
        entry = tk.Entry(root, show="•", width=28)
        entry.pack(padx=20, pady=5)
        result = []

        def submit(event=None):
            result.append(entry.get())
            root.quit()

        buttons = tk.Frame(root)
        buttons.pack(padx=20, pady=15)
        tk.Button(buttons, text="Logga in", command=submit).pack(side="left", padx=5)
        tk.Button(buttons, text="Avbryt", command=root.quit).pack(side="left", padx=5)
        root.bind("<Return>", submit)
        root.bind("<Escape>", lambda event: root.quit())
        root.protocol("WM_DELETE_WINDOW", root.quit)
        root.after(180000, root.quit)
        root.after(200, lambda: (root.focus_force(), entry.focus_set()))
        root.mainloop()
        return result[0] if result else None
    except tk.TclError:
        raise E37Error("MFA-fönstret stängdes. Kör kommandot igen.") from None
    finally:
        root.destroy()


def _fallback(message):
    if sys.platform != "darwin":
        raise E37Error("Kan inte visa MFA-fönstret. Kör i en terminal med E37_MFA_MODE=terminal, "
                       "eller installera Python med tkinter på din dator.")
    script = ('on run argv\n'
              'display dialog (item 1 of argv) default answer "" with hidden answer '
              'with title "E37 MFA" buttons {"Avbryt", "Logga in"} '
              'default button "Logga in" cancel button "Avbryt" giving up after 180\n'
              'if gave up of result then return ""\n'
              'return text returned of result\nend run')
    try:
        result = subprocess.run(["osascript", "-e", script, message],
                                capture_output=True, text=True, timeout=190)
    except (OSError, subprocess.TimeoutExpired):
        raise E37Error("Kunde inte läsa MFA-koden. Kör kommandot igen i en terminal.") from None
    return result.stdout.strip() if result.returncode == 0 else None
