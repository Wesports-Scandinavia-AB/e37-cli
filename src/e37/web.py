"""
E37 Admin through the web UI, signed in as the person.

E37's REST API has orders and gift cards and little else, and it needs an API key
nobody can currently create. E37 Admin itself shows everything the signed-in user
may see, so this module signs in with the person's own e-mail and password and
reads what the UI offers. Mapped and verified 2026-10-07; see docs/web.md.

NO BROWSER NEEDED SO FAR. Login is a plain form POST and the reports come as JSON
from a handler the UI itself calls, so urllib and a cookie jar are enough. Scrapling
(the `web` extra) stays reserved for pages that turn out to need a real browser.

ONE SESSION PER RUN. The site picker is server-side session state, so two runs
sharing a session would switch shop under each other. A Session is made, used and
dropped; nothing here is global and nothing is written to disk.

READ ONLY. Nothing in this module posts a form that saves. Keep it that way unless
a command explicitly exists to change something, with --dry-run first.
"""

import http.cookiejar
import json
import re
from html import unescape
from urllib import parse, request
from urllib.error import HTTPError, URLError

from . import E37Error, __version__

BASE_URL = "https://admin3.e37.se/"
USER_AGENT = f"Mozilla/5.0 (compatible; e37-cli/{__version__}; +https://github.com/Wesports-Scandinavia-AB/e37-cli)"
REPORTS_PAGE = "workspace/workwith/reports.aspx"
REPORT_HANDLER = "custom/orderReportHandler.ashx"
FILE_TYPE_JSON = "5"

ORDERFLOW_REPORT = "28"


def base_url(account):
    """The admin host for an account: admin2 or admin3, taken from its API base."""
    api = account.get("baseUrl") or ""
    m = re.match(r"(https://admin\d\.e37\.se/)", api)
    return m.group(1) if m else BASE_URL


class Session:
    """A signed-in E37 Admin session for one account."""

    def __init__(self, account, timeout=120):
        web = account.get("web") or {}
        if not (account.get("webshopId") and web.get("email") and web.get("password")):
            raise E37Error(f"E37-kontot {account['name']} saknar webbinloggning (webbshop-ID, e-post, lösenord). "
                           f"Lägg till den med: e37 account add {account['name']} --dialog")
        self.account = account
        self.base = base_url(account)
        self.timeout = timeout
        self._jar = http.cookiejar.CookieJar()
        self._op = request.build_opener(request.HTTPCookieProcessor(self._jar))
        self._login(account["webshopId"], web["email"], web["password"])

    # ---- transport -----------------------------------------------------------

    def _open(self, path, data=None):
        url = path if path.startswith("http") else self.base + path.lstrip("/")
        body = parse.urlencode(data).encode() if data is not None else None
        req = request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
        try:
            return self._op.open(req, timeout=self.timeout)
        except HTTPError as e:
            raise E37Error(f"E37 Admin svarade HTTP {e.code} på {url.split('?')[0]}")
        except URLError as e:
            raise E37Error(f"Nådde inte {self.base}: {e.reason}")

    def _page(self, path, data=None):
        with self._open(path, data) as r:
            return r.geturl(), r.read().decode("utf-8", errors="replace")

    # ---- login ---------------------------------------------------------------

    def _login(self, shop_id, email, password):
        final, html = self._page(self.base)
        if "ddlSitePicker" in html:
            return
        data = _hidden(html)
        # btnLogin is an <input type=image>: a browser posts the click position.
        data.update({"tbAccountName": shop_id, "tbEmail": email, "tbPassword": password,
                     "btnLogin.x": "10", "btnLogin.y": "10"})
        _, html = self._page(final, data)
        if "ddlSitePicker" not in html:
            raise E37Error(f"Inloggningen i E37 Admin misslyckades för {self.account['name']}. "
                           f"Kontrollera webbshop-ID, e-post och lösenord med: "
                           f"e37 account add {self.account['name']} --dialog")
        self._home = html

    def sites(self):
        """[(id, name)] for every site this login can see; the default marked by E37 in the name."""
        m = re.search(r'<select[^>]*ddlSitePicker[^>]*>(.*?)</select>', self._home, re.S)
        return [(v, unescape(t).strip()) for v, t in _options(m.group(1))] if m else []

    # ---- reports -------------------------------------------------------------

    def report_types(self):
        """[(id, title)] of the reports E37 Admin offers this login."""
        _, html = self._page(REPORTS_PAGE)
        m = re.search(r'<select[^>]*ddlReportType[^>]*>(.*?)</select>', html, re.S)
        return [(v, unescape(t).strip()) for v, t in _options(m.group(1)) if v] if m else []

    def report_settings(self, report_type):
        """The settings one report takes: [{id, kind, label, options, default}].

        Selecting a report type is a postback that renders its settings as divs
        with data-setting-id; the UI joins their values into the download URL.
        """
        _, html = self._page(REPORTS_PAGE)
        data = _form(html)
        data.update({"ctl00$cph1$ddlReportType": str(report_type),
                     "__EVENTTARGET": "ctl00$cph1$ddlReportType", "__EVENTARGUMENT": ""})
        _, html = self._page(REPORTS_PAGE, data)
        return _settings(html)

    def report(self, report_type, values):
        """Download one report as parsed JSON.

        `values` maps setting id to value; a missing setting is sent empty, a
        missing checkbox as false — the same string the UI's own JavaScript builds.
        """
        settings = self.report_settings(report_type)
        if not settings:
            raise E37Error(f"Rapporttyp {report_type} finns inte, eller har inga inställningar.")
        parts = []
        for s in settings:
            v = values.get(s["id"], s["default"])
            if s["kind"] == "checkbox":
                v = "true" if v in (True, "true", "1", "ja", "yes") else "false"
            parts.append(f"{s['id']}:{'' if v is None else v}")
        q = parse.urlencode({"data": "¤".join(parts), "reportType": str(report_type), "fileType": FILE_TYPE_JSON})
        with self._open(f"{REPORT_HANDLER}?{q}") as r:
            ctype = r.headers.get("Content-Type", "")
            body = r.read()
        if "json" not in ctype:
            raise E37Error(f"E37 gav inte JSON för rapport {report_type} (fick {ctype or 'okänt'}). "
                           f"Kontrollera inställningarna med: e37 report show {report_type}")
        return json.loads(body.decode("utf-8-sig"))

    def orderflow(self, start, end, mode="completed", site=None, extra=True):
        """Rows of the order flow report, as the API's report would give them and more.

        `extra` ticks every optional column except customer details: order status,
        payment method, shipping fee, ERP sync status, marketplace. Customer fields
        are personal data and stay off unless asked for.
        """
        values = {
            "dateInterval": f"{start:%Y-%m-%d %H:%M},{end:%Y-%m-%d %H:%M}",
            "orderTimestampMode": mode,
            "site": site or "",
        }
        if extra:
            for k in ("includeGiftCardAndToPay", "includeShippingFee", "includeOrderStatusColumn",
                      "includeOtherStatus", "includePaymentMethod", "includeExternalMarketplace"):
                values[k] = True
        return (self.report(ORDERFLOW_REPORT, values) or {}).get("rows", [])


# ---- HTML helpers --------------------------------------------------------------

def _options(select_html):
    return re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', select_html)


def _hidden(html):
    return {n: unescape(v) for n, v in
            re.findall(r'<input type="hidden" name="(__\w+)" id="__\w+" value="([^"]*)"', html)}


def _form(html):
    """Every field as a browser would post it, minus buttons: what a postback needs."""
    out = {}
    for m in re.finditer(r"<input([^>]*)>", html):
        attrs = m.group(1)
        a = dict(re.findall(r'(\w+)="([^"]*)"', attrs))
        kind, name = a.get("type", "text"), a.get("name")
        if not name or kind in ("image", "submit", "button", "file", "password"):
            continue
        if kind in ("checkbox", "radio") and "checked" not in attrs:
            continue
        out[name] = unescape(a.get("value", "on" if kind == "checkbox" else ""))
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        sel = (re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', m.group(2))
               or re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', m.group(2))
               or re.search(r'<option[^>]*value="([^"]*)"', m.group(2)))
        out[m.group(1)] = unescape(sel.group(1)) if sel else ""
    return out


def _settings(html):
    """Parse the data-setting divs of a selected report into a description per setting."""
    out = []
    starts = [m for m in re.finditer(r'<div[^>]*data-setting-type="[^"]*"[^>]*>', html)]
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else m.end() + 4000
        block = html[m.start():end]
        sid = re.search(r'data-setting-id="([^"]*)"', m.group(0)).group(1)
        label = re.search(r"<label[^>]*>([^<]*)</label>", block)
        options, default, kind = [], "", "text"
        sel = re.search(r"<select[^>]*>(.*?)</select>", block, re.S)
        texts = re.findall(r'<input[^>]*type="text"[^>]*value="([^"]*)"', block)
        if 'type="radio"' in block:
            kind = "radio"
            options = [(v, "") for v in re.findall(r'type="radio"[^>]*value="([^"]*)"', block)]
            ch = re.search(r'type="radio"[^>]*value="([^"]*)"[^>]*checked', block)
            default = ch.group(1) if ch else ""
        elif 'type="checkbox"' in block:
            kind = "checkbox"
            default = "true" if re.search(r'type="checkbox"[^>]*checked', block) else "false"
        elif sel:
            kind = "select"
            options = [(v, unescape(t).strip()) for v, t in _options(sel.group(1))]
            ch = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', sel.group(1))
            default = ch.group(1) if ch else (options[0][0] if options else "")
        elif texts:
            kind = "date-interval" if len(texts) == 2 else "text"
            default = ",".join(unescape(t) for t in texts)
        lab = unescape(label.group(1)).strip().rstrip(":") if label else ""
        if not lab:
            prev = re.sub(r"<[^>]+>", " ", html[max(0, m.start() - 400):m.start()])
            lab = unescape(prev).split(":")[-2].strip()[-60:] if ":" in prev else ""
        out.append({"id": sid, "kind": kind, "label": lab, "options": options, "default": default})
    return out
