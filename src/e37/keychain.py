"""
The operating system's own keychain, one entry per E37 instance.

E37 logins are personal: an API key someone created, an e-mail and password that
are one person's admin account. So they belong in that person's keychain — not in
a file next to the code, not in a shared vault — where the OS ties them to the
signed-in user and nobody else on the machine can read them.

  Windows  Credential Manager, through advapi32 via ctypes. Generic credentials
           named `e37-cli:<instance>`, encrypted with DPAPI for the Windows user.
  macOS    The login keychain, through /usr/bin/security. Generic passwords with
           service `e37-cli` and account `<instance>`.

No dependency: `keyring` would do both, but this package has none and ctypes plus
one system binary cover what we need.

ON MACOS THE VALUE NEVER TOUCHES ARGV. `security add-generic-password -w VALUE`
would put it in the process list for every user to read, so the write goes through
`security -i` with the command on stdin, and the value hex-encoded (-X) so no
quoting of JSON is involved.
"""

import json
import subprocess
import sys

from . import E37Error

SERVICE = "e37-cli"


def backend():
    if sys.platform == "win32":
        return "Windows Credential Manager"
    if sys.platform == "darwin":
        return "macOS-nyckelringen"
    return None


def _unsupported():
    raise E37Error(f"Ingen nyckelring för {sys.platform}. Använd E37_*-miljövariabler.")


# ---- public -----------------------------------------------------------------

def get(name):
    """The stored value for one instance as a dict, or None."""
    raw = _win_get(name) if sys.platform == "win32" else _mac_get(name) if sys.platform == "darwin" else _unsupported()
    return json.loads(raw) if raw else None


def put(name, value):
    raw = json.dumps(value, ensure_ascii=False)
    if sys.platform == "win32":
        _win_put(name, raw)
    elif sys.platform == "darwin":
        _mac_put(name, raw)
    else:
        _unsupported()


def delete(name):
    """True if something was removed."""
    if sys.platform == "win32":
        return _win_delete(name)
    if sys.platform == "darwin":
        return _mac_delete(name)
    _unsupported()


def names():
    """Every instance stored, sorted."""
    if sys.platform == "win32":
        return sorted(_win_names())
    if sys.platform == "darwin":
        return sorted(_mac_names())
    return []


# ---- Windows ------------------------------------------------------------------

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    CRED_TYPE_GENERIC = 1
    # Despite the name this is per user: it survives logoff and stays on this
    # machine, where ENTERPRISE would roam with the profile.
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _PCRED = ctypes.POINTER(_CREDENTIAL)
    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    _advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_PCRED)]
    _advapi.CredReadW.restype = wintypes.BOOL
    _advapi.CredWriteW.argtypes = [_PCRED, wintypes.DWORD]
    _advapi.CredWriteW.restype = wintypes.BOOL
    _advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _advapi.CredDeleteW.restype = wintypes.BOOL
    _advapi.CredEnumerateW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                       ctypes.POINTER(ctypes.POINTER(_PCRED))]
    _advapi.CredEnumerateW.restype = wintypes.BOOL
    _advapi.CredFree.argtypes = [ctypes.c_void_p]
    _advapi.CredFree.restype = None


def _target(name):
    return f"{SERVICE}:{name}"


def _win_error(what):
    err = ctypes.get_last_error()
    return E37Error(f"Credential Manager: {what} misslyckades ({ctypes.FormatError(err).strip()})")


def _win_get(name):
    p = _PCRED()
    if not _advapi.CredReadW(_target(name), CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        raise _win_error("läsning")
    try:
        c = p.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-8")
    finally:
        _advapi.CredFree(p)


def _win_put(name, raw):
    blob = raw.encode("utf-8")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = _CREDENTIAL()
    c.Type = CRED_TYPE_GENERIC
    c.TargetName = _target(name)
    c.Comment = "e37-cli: E37 instance credentials"
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    c.Persist = CRED_PERSIST_LOCAL_MACHINE
    c.UserName = name
    if not _advapi.CredWriteW(ctypes.byref(c), 0):
        raise _win_error("skrivning")


def _win_delete(name):
    if _advapi.CredDeleteW(_target(name), CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == ERROR_NOT_FOUND:
        return False
    raise _win_error("borttagning")


def _win_names():
    count = wintypes.DWORD()
    creds = ctypes.POINTER(_PCRED)()
    if not _advapi.CredEnumerateW(f"{SERVICE}:*", 0, ctypes.byref(count), ctypes.byref(creds)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return []
        raise _win_error("listning")
    try:
        prefix = SERVICE + ":"
        return [creds[i].contents.TargetName[len(prefix):] for i in range(count.value)]
    finally:
        _advapi.CredFree(creds)


# ---- macOS ----------------------------------------------------------------------

def _security(args, stdin=None):
    return subprocess.run(["/usr/bin/security", *args], input=stdin, capture_output=True, text=True)


def _mac_get(name):
    r = _security(["find-generic-password", "-s", SERVICE, "-a", name, "-w"])
    if r.returncode == 44:  # errSecItemNotFound
        return None
    if r.returncode:
        raise E37Error(f"Nyckelringen: läsning misslyckades ({r.stderr.strip()})")
    return r.stdout.rstrip("\n")


def _mac_put(name, raw):
    # -U updates an existing item in place. The account name is a slug we
    # validated, so it needs no quoting; the value goes hex-encoded.
    cmd = f"add-generic-password -U -s {SERVICE} -a {name} -X {raw.encode('utf-8').hex()}\n"
    r = _security(["-i"], stdin=cmd)
    if r.returncode or "error" in r.stderr.lower():
        raise E37Error(f"Nyckelringen: skrivning misslyckades ({r.stderr.strip()})")


def _mac_delete(name):
    r = _security(["delete-generic-password", "-s", SERVICE, "-a", name])
    if r.returncode == 44:
        return False
    if r.returncode:
        raise E37Error(f"Nyckelringen: borttagning misslyckades ({r.stderr.strip()})")
    return True


def _mac_names():
    """Attributes only — dump-keychain without -d never decrypts or prompts."""
    r = _security(["dump-keychain"])
    out, acct, svce = [], None, None
    for line in r.stdout.splitlines() + ["keychain:"]:
        line = line.strip()
        if line.startswith("keychain:"):
            if svce == SERVICE and acct:
                out.append(acct)
            acct = svce = None
        elif line.startswith('"acct"<blob>="'):
            acct = line.split('="', 1)[1].rstrip('"')
        elif line.startswith('"svce"<blob>="'):
            svce = line.split('="', 1)[1].rstrip('"')
    return out
