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
        body = parse.urlencode(data, doseq=True).encode() if data is not None else None
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


    # ---- one order -------------------------------------------------------------

    def order(self, order_id):
        """One order as E37 Admin's order window shows it, or None if E37 has none.

        The window opens with a postback (`viewOrder?ID` on orders.aspx), which a
        plain synchronous POST renders into the page. Only that postback is sent.
        The window also holds buttons that change the order — activate, cancel,
        change delivery, resend confirmation, set status — and none of them is
        ever posted from here.
        """
        _, html = self._page(ORDERS_PAGE)
        data = _form(html)
        data.update({"__EVENTTARGET": "__Page", "__EVENTARGUMENT": f"viewOrder?{int(order_id)}"})
        _, html = self._page(ORDERS_PAGE, data)
        return _parse_order(html, int(order_id))

    # ---- sites ---------------------------------------------------------------

    def switch_site(self, site_id):
        """Make one site current for this session. Site-bound fields (texts per
        language) are read and written for the current site, so callers check
        current_site() again before every write rather than trusting this."""
        _, html = self._page(ARTICLES_PAGE)
        if _current_site(html) == str(site_id):
            self._articles = html
            return
        data = _form_full(html)
        data.update({"ctl00$ddlSitePicker": str(site_id), "__EVENTTARGET": "ctl00$ddlSitePicker", "__EVENTARGUMENT": ""})
        _, html = self._page(ARTICLES_PAGE, data)
        if _current_site(html) != str(site_id):
            raise E37Error(f"Kunde inte byta till webbplats {site_id} (står på {_current_site(html)}).")
        self._articles = html

    def current_site(self):
        _, html = self._page(ARTICLES_PAGE)
        self._articles = html
        return _current_site(html)

    # ---- article variants ----------------------------------------------------

    def find_variant(self, art_nr):
        """The variant id for an exact article number. Exactly one match or an error."""
        _, html = self._page(ARTICLES_PAGE)
        data = _form_full(html)
        data.update({"ctl00$cph1$settingstabs$tabSearch$txtSearch": art_nr,
                     "ctl00$cph1$settingstabs$tabSearch$btnArticleSearch.x": "5",
                     "ctl00$cph1$settingstabs$tabSearch$btnArticleSearch.y": "5"})
        _, html = self._page(ARTICLES_PAGE, data)
        # The search matches substrings; only an exact article number counts.
        hits = re.findall(r'<tr[^>]*data-article-variant-id="(\d+)"[^>]*data-article-variant-nr="%s"' % re.escape(art_nr), html)
        if len(set(hits)) != 1:
            raise E37Error(f"hittade {len(set(hits))} varianter med exakt artikelnummer {art_nr}")
        self._articles = html
        return hits[0]

    def _open_variant(self, variant_id):
        """The articles page with one variant's edit window rendered in it."""
        data = _form_full(self._articles)
        data.update({"__EVENTTARGET": "__Page", "__EVENTARGUMENT": f"a_id={int(variant_id)};"})
        _, html = self._page(ARTICLES_PAGE, data)
        if "Redigera artikelvariant" not in html:
            raise E37Error(f"variant {variant_id} gick inte att öppna")
        return html

    def delivery_text(self, art_nr):
        """(site_id, language, text) of 'Leverans-/beställningstid, om slut i lager'
        for one variant on the current site."""
        html = self._open_variant(self.find_variant(art_nr))
        name, lang, value = _delivery_field(html)
        return _current_site(html), lang, value

    def set_delivery_text(self, art_nr, text, site_id):
        """Write the out-of-stock delivery text for one variant on one site, then prove it.

        A save in E37 Admin posts the whole form. So the form is serialised the way
        a browser would, only the one field is changed, and afterwards the variant
        is opened again and EVERY field compared with before: the target must hold
        the new text and nothing else may have moved. Anything else is an error
        the caller must stop on. Returns (old, new_as_read_back).
        """
        if _current_site(self._articles) != str(site_id):
            self.switch_site(site_id)
        variant_id = self.find_variant(art_nr)
        html = self._open_variant(variant_id)
        if _current_site(html) != str(site_id):
            raise E37Error(f"fel webbplats ({_current_site(html)}) inför skrivning, avbryter")
        name, lang, old = _delivery_field(html)
        before = _form_full(html)
        if old == text:
            self._articles = html
            return old, old
        data = dict(before)
        data[name] = text
        # What the dialog's own change handler does when a field is edited.
        for k in data:
            if k.startswith(_VARIANT_PREFIX) and k.endswith("$PopupTab3$changesMadeHiddenField"):
                data[k] = "1"
        data[_VARIANT_PREFIX + "$btnSave.x"] = "5"
        data[_VARIANT_PREFIX + "$btnSave.y"] = "5"
        _, saved = self._page(ARTICLES_PAGE, data)
        self._articles = saved
        if "Redigera artikelvariant" in saved and re.search(r'class="[^"]*(?:error|validator)[^"]*"[^>]*>[^<]{3,}', saved):
            raise E37Error("E37 visade ett valideringsfel vid sparning")
        # Proof: reopen and compare everything.
        self.find_variant(art_nr)
        after_html = self._open_variant(variant_id)
        after = _form_full(after_html)
        _, _, now = _delivery_field(after_html)
        changed = sorted(k for k in set(before) | set(after)
                         if k.startswith(_VARIANT_PREFIX) and k != name and not k.endswith("changesMadeHiddenField")
                         and not k.endswith("$hidden" + lang) and before.get(k) != after.get(k))
        if changed:
            raise E37Error("ANDRA FÄLT ÄNDRADES vid sparning: " + ", ".join(c.split("$")[-1] for c in changed[:8])
                           + ". Stanna och kontrollera varianten i E37 Admin.")
        return old, now


ARTICLES_PAGE = "workspace/workwith/articles/list.aspx"
_VARIANT_PREFIX = "ctl00$cph1$mod1$pnl$usrCtrl"


def _current_site(html):
    m = re.search(r'<select[^>]*ddlSitePicker[^>]*>(.*?)</select>', html, re.S)
    sel = re.search(r'<option[^>]*selected="selected"[^>]*value="([^"]*)"', m.group(1)) if m else None
    sel = sel or (re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', m.group(1)) if m else None)
    return sel.group(1) if sel else None


def _delivery_field(html):
    """(post name, language, value) of the out-of-stock delivery text — not the
    in-stock one, not the hidden mirror."""
    for m in re.finditer(r'<input[^>]*name="([^"]*\$tbDeliveryTimeText\$(\w+))"[^>]*>', html):
        lang = m.group(2)
        if lang.startswith("hidden"):
            continue
        v = re.search(r'value="([^"]*)"', m.group(0))
        return m.group(1), lang, unescape(v.group(1)) if v else ""
    raise E37Error("hittade inte fältet 'Leverans-/beställningstid, om slut i lager'")


def _form_full(html):
    """The whole form as a browser would post it, so a save does not blank fields.

    Unlike _form this keeps textareas, every selected option of a multi-select,
    the first option of a single select without a selection, and drops disabled
    controls (browsers do not post them). Buttons are never included; the caller
    adds the one being "clicked".
    """
    out = {}
    for m in re.finditer(r"<input\b([^>]*)>", html):
        attrs = m.group(1)
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        kind, name = a.get("type", "text").lower(), a.get("name")
        if not name or kind in ("image", "submit", "button", "file", "reset") or re.search(r'\bdisabled\b', attrs):
            continue
        if kind in ("checkbox", "radio") and not re.search(r'\bchecked\b', attrs):
            continue
        out[name] = unescape(a.get("value", "on" if kind in ("checkbox", "radio") else ""))
    for m in re.finditer(r"<textarea\b([^>]*)>(.*?)</textarea>", html, re.S):
        name = re.search(r'name="([^"]*)"', m.group(1))
        if name and not re.search(r'\bdisabled\b', m.group(1)):
            body = m.group(2)
            out[name.group(1)] = unescape(body[1:] if body.startswith("\n") else body)
    for m in re.finditer(r"<select\b([^>]*)>(.*?)</select>", html, re.S):
        name = re.search(r'name="([^"]*)"', m.group(1))
        if not name or re.search(r'\bdisabled\b', m.group(1)):
            continue
        opts = re.findall(r"<option\b([^>]*)>", m.group(2))
        chosen = [re.search(r'value="([^"]*)"', o) for o in opts if re.search(r'\bselected\b', o)]
        chosen = [c.group(1) for c in chosen if c]
        if not chosen and opts and "multiple" not in m.group(1):
            first = re.search(r'value="([^"]*)"', opts[0])
            chosen = [first.group(1)] if first else []
        if chosen:
            # urlencode with doseq needs a list for multi-selects; one value stays a str.
            out[name.group(1)] = [unescape(c) for c in chosen] if len(chosen) > 1 else unescape(chosen[0])
    return out


ORDERS_PAGE = "workspace/workwith/orders.aspx"
_TAB1 = "ctl00_cph1_ModalPopup1_pnl_usrCtrl_PopupTab1"


def _text(fragment):
    """Visible text of an HTML fragment, <br> as newline, whitespace tidied."""
    s = re.sub(r"<br\s*/?>", "\n", fragment)
    s = unescape(re.sub(r"<[^>]+>", " ", s))
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _amount(s):
    """'1 099 kr' or '879,20 kr' -> 1099.0 / 879.2; None when there is no number."""
    m = re.search(r"-?[\d\s\xa0]+(?:,\d+)?", s or "")
    if not m or not re.search(r"\d", m.group(0)):
        return None
    return float(re.sub(r"[\s\xa0]", "", m.group(0)).replace(",", "."))


def _when_text(s):
    """E37 writes recent times as 'Idag 22:53' / 'Igår 08:10'; make them dates."""
    from datetime import date, timedelta
    s = (s or "").strip()
    for word, days in (("Idag", 0), ("Igår", 1)):
        if s.startswith(word):
            return f"{date.today() - timedelta(days=days):%Y-%m-%d}{s[len(word):]}"
    return s


def _parse_order(html, order_id):
    start = html.find(f'id="{_TAB1}"')
    if start < 0:
        return None
    end = html.find('id="ctl00_cph1_ModalPopup1_pnl_usrCtrl_PopupTab2"', start)
    tab = re.sub(r"<script.*?</script>|<style.*?</style>", "", html[start:end if end > 0 else None], flags=re.S)

    pieces = {}
    for m in re.finditer(r'<div[^>]*class="piece"[^>]*>(.*?)<span[^>]*class="bigtext"[^>]*>(.*?)</span>', tab, re.S):
        pieces[_text(m.group(1)).rstrip(":")] = _text(m.group(2))
    number = pieces.pop("Ordernummer", "")
    if str(order_id) != number.strip():
        return None
    fields = {_text(k).rstrip(":"): _text(v) for k, v in
              re.findall(r"<tr[^>]*>\s*<td[^>]*>([^<]{2,40}:)\s*</td>\s*<td[^>]*>(.*?)</td>\s*</tr>", tab, re.S)}

    addresses, contact = {}, {}
    for label, body in re.findall(r'<div class="addressItem"><label class="cart">([^<]*)</label>(.*?)</div>', tab, re.S):
        value = _text(body)
        (addresses if "\n" in value or "adress" in label.lower() else contact)[unescape(label)] = value

    rows = []
    cart = re.search(r'id="%s_cartTable".*?</table>' % _TAB1, tab, re.S)
    for tr in re.findall(r'<tr[^>]*class="cartRow[^"]*"[^>]*>(.*?)</tr>', cart.group(0) if cart else "", re.S):
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 6:
            rows.append({"sku": cells[0], "name": cells[1].replace("\n", " / "), "quantity": _amount(cells[3]),
                         "unit_price": _amount(cells[4]), "sum": _amount(cells[5]), "price_text": cells[5]})

    summary = {}
    osum = re.search(r'class="orderSummary".*?</table>', tab, re.S)
    for label, value in re.findall(r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>", osum.group(0) if osum else "", re.S):
        summary[_text(label)] = _amount(_text(value))

    def box(name):
        m = re.search(r'id="%s_roundedBox%s".*?<span class="subtitle">\s*-\s*([^<]*)</span>' % (_TAB1, name), tab, re.S)
        return unescape(m.group(1)).strip() if m else None

    status = re.search(r'<select[^>]*ddlOrderStatus[^>]*>(.*?)</select>', tab, re.S)
    chosen = re.search(r'<option[^>]*selected[^>]*>([^<]*)', status.group(1)) if status else None
    notes_box = re.search(r'id="%s_roundedBoxComments_divContent"[^>]*>(.*?)<input' % _TAB1, tab, re.S)

    return {
        "order_id": order_id,
        "order_timestamp": _when_text(pieces.pop("Datum & tid", "")),
        "customer_number": pieces.pop("Kundnummer", None),
        "order_status": unescape(chosen.group(1)).strip() if chosen else None,
        "site": fields.get("Webbplats"),
        "customer_type": fields.get("Kundtyp"),
        "vat": fields.get("Momsland och typ"),
        "accepts_marketing": fields.get("Accepterat marknadsföring"),
        "referer": fields.get("Hänvisning"),
        "source": fields.get("Källa"),
        "order_confirmation": (fields.get("Orderbekräftelse") or "").split(" - ")[0] or None,
        "payment": {"method": box("Payment"), "status": fields.get("Status"), "invoice_number": fields.get("Fakturanr")},
        "delivery": {"method": box("Delivery"), "pickup_point": _text(re.search(
            r"<label>Utlämningsställe:</label>(.*?)</div>", tab, re.S).group(1)) if "Utlämningsställe:" in tab else None},
        "other": pieces,          # e.g. ERP sync status, labelled as E37 labels it
        "addresses": addresses,
        "contact": contact,
        "rows": rows,
        "summary": summary,
        "notes": (_text(notes_box.group(1)) or None) if notes_box else None,
    }


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
