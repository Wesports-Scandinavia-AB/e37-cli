"""
E37 Admin: the order flow report and the Triton Admin REST API.

Two mechanisms, one API key, two ways of presenting it (see docs/order-api.md):

  - the order flow report, `/reports/orderflow`, takes the key as `key=` in the
    query string, together with the shop's `account` slug;
  - the REST API, `/orders/{id}`, takes HTTP Basic with the webshop ID as user
    and the same key as password.

NOT YET EXERCISED. As of 2026-10-07 nobody has a working key — creating one in
E37 Admin fails — so every request shape here is taken from E37's OpenAPI spec
and screenshots, not from a live response. Expect the first real call to need
adjusting, and update docs/order-api.md when it does.

THE KEY IN THE URL. The report endpoint wants the key in the query string, where
it lands in every log between here and E37. This module therefore never prints
a request URL, and every error it raises is built from the path alone.

CREDENTIALS. E37 logins are personal, so they live in the user's own keychain
(see keychain.py), one entry per E37 instance, never in a file. Resolution order:

  1. E37_ACCOUNT / E37_WEBSHOP_ID / E37_API_KEY / E37_ADMIN_BASE_URL — one shop,
     for CI or a one-off script
  2. the keychain, filled with `e37 account add NAME`

An entry is {"webshopId", "baseUrl", "account", "key", "web": {"email",
"password"}}. Every part but the name is optional and checked where it is used:
the report needs `key`, the REST API also `webshopId`, the web UI `web`.

`name` is what you type on the command line; `account` is E37's slug for the
report. They are usually the same, so `account` defaults to `name`. Whether one
key covers several shops is an open question to E37, so nothing here assumes it.

TIMESTAMPS. `order_timestamp` and the `dateInterval` filter carry no offset and
are almost certainly Stockholm local time. Windows has no tz database for
`zoneinfo` and this package has no dependencies, so windows are built from this
machine's local clock — which is Swedish time on every machine that runs this.
"""

import base64
import json
import os
import re
from datetime import datetime, timedelta
from urllib import parse, request
from urllib.error import HTTPError, URLError

from . import E37Error, __version__, keychain

USER_AGENT = f"e37-cli/{__version__} (+https://github.com/Wesports-Scandinavia-AB/e37-cli)"
DEFAULT_BASE_URL = "https://admin3.e37.se/api"

ORDER_STATUS = {
    1: "NewOrder",
    2: "Cancelled",
    3: "Delivered",
    4: "PackingSlipPrinted",
    5: "ChangeOrder",
    6: "PartiallyDelivered",
    -1: "Custom",
}


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def accounts():
    """Every configured instance, environment first.

    A half configured instance fails loudly where it is used instead of falling
    back to another one: reading the wrong shop's orders is a mistake nothing
    downstream would reveal.
    """
    env_key = os.environ.get("E37_API_KEY")
    if env_key:
        name = os.environ.get("E37_ACCOUNT") or "env"
        return [_checked(name, {
            "account": os.environ.get("E37_ACCOUNT"),
            "webshopId": os.environ.get("E37_WEBSHOP_ID"),
            "key": env_key,
            "baseUrl": os.environ.get("E37_ADMIN_BASE_URL"),
        })]

    names = keychain.names()
    if not names:
        raise E37Error("Inga E37-konton. Lägg till ett med: e37 account add NAMN "
                       "(eller sätt E37_ACCOUNT/E37_WEBSHOP_ID/E37_API_KEY).")
    return [_checked(n, keychain.get(n) or {}) for n in names]


def _checked(name, a):
    web = a.get("web") or {}
    return {
        "name": name,
        "account": a.get("account") or name,
        "webshopId": str(a["webshopId"]) if a.get("webshopId") else None,
        "key": a.get("key") or None,
        "baseUrl": str(a.get("baseUrl") or DEFAULT_BASE_URL).rstrip("/"),
        "web": {"email": web.get("email"), "password": web.get("password")} if web.get("email") else None,
    }


def _need_key(account):
    if not account["key"]:
        raise E37Error(f"E37-kontot {account['name']} saknar API-nyckel. "
                       f"Lägg till den med: e37 account add {account['name']}")


def resolve_account(ref=None):
    """One shop by name, or the only one when there is just one."""
    rows = accounts()
    if ref is None:
        if len(rows) == 1:
            return rows[0]
        known = ", ".join(a["name"] for a in rows)
        raise E37Error(f"Flera E37-konton, välj ett med --account: {known}")
    hits = [a for a in rows if ref.lower() in (a["name"].lower(), a["account"].lower())]
    if not hits:
        known = ", ".join(a["name"] for a in rows)
        raise E37Error(f"Inget E37-konto {ref!r}. Finns: {known}")
    return hits[0]


def _get(account, path, params=None, basic=False, timeout=60):
    url = account["baseUrl"] + path + ("?" + parse.urlencode(params) if params else "")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    _need_key(account)
    if basic:
        if not account["webshopId"]:
            raise E37Error(f"E37-kontot {account['name']} saknar webshopId, som REST-API:t kräver.")
        cred = base64.b64encode(f"{account['webshopId']}:{account['key']}".encode()).decode()
        headers["Authorization"] = "Basic " + cred
    try:
        with request.urlopen(request.Request(url, headers=headers), timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as e:
        # Never the URL: for the report it carries the key.
        body = e.read().decode(errors="replace")[:400]
        if e.code in (401, 403):
            raise E37Error(f"E37 avvisade nyckeln för {account['name']} ({e.code}).")
        if e.code == 404:
            return None
        raise E37Error(f"GET {path} ({account['name']}): HTTP {e.code}: {body}")
    except URLError as e:
        raise E37Error(f"Nådde inte {account['baseUrl']}: {e.reason}")
    return json.loads(raw) if raw else None


def half_hour_window(now=None):
    """The previous closed half hour — E37's recommended polling window.

    Run at 14:02 and get 13:30–14:00. Filtering on completion time is what makes
    back-to-back windows gap-free; see "Polling recipe" in docs/order-api.md.
    """
    now = now or datetime.now()
    end = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0)
    return end - timedelta(minutes=30), end


def orderflow(account, start, end, mode="completed"):
    """Rows from the order flow report for one shop and one time window."""
    interval = f"{start:%Y-%m-%d %H:%M},{end:%Y-%m-%d %H:%M}"
    data = _get(account, "/reports/orderflow", {
        "account": account["account"],
        "key": account["key"],
        "dateInterval": interval,
        "orderTimestampMode": mode,
    })
    return (data or {}).get("rows", [])


def order(account, order_id):
    """Full order from GET /orders/{id}, or None if E37 does not know it."""
    return _get(account, f"/orders/{int(order_id)}", basic=True)


def order_status(account, order_id):
    """Current status only, from GET /orders/{id}/status, or None."""
    return _get(account, f"/orders/{int(order_id)}/status", basic=True)
