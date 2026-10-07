import argparse
import json
import sys
from datetime import datetime

from . import E37Error, admin, keychain, shop, web


def _dump(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _when(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError(f"väntade 'ÅÅÅÅ-MM-DD TT:MM', fick {s!r}")


# ---- account -----------------------------------------------------------------

def _public(r):
    """An account as it may be shown: which secrets exist, never their values."""
    return {
        "name": r["name"], "account": r["account"], "webshopId": r["webshopId"], "baseUrl": r["baseUrl"],
        "apiKey": bool(r["key"]), "webEmail": (r["web"] or {}).get("email"),
    }


def cmd_account_list(a):
    rows = admin.accounts()
    if a.json:
        _dump([_public(r) for r in rows])
        return 0
    print(f"lagras i  {keychain.backend() or 'miljövariabler'}\n")
    for r in map(_public, rows):
        print(f"{r['name']:<16} webshopId={r['webshopId'] or '-':<8} nyckel={'ja' if r['apiKey'] else 'nej':<4} "
              f"webb={r['webEmail'] or '-':<28} {r['baseUrl']}")
    return 0


def _ask(label, current, secret=False):
    """Prompt once; Enter keeps the current value. Secrets never echo or print."""
    import getpass
    hint = (" [sparad]" if current else "") if secret else (f" [{current}]" if current else "")
    prompt = f"{label}{hint}: "
    # getpass writes its prompt to the terminal itself; input() needs stderr so
    # that stdout stays clean for anyone capturing it.
    if secret:
        value = getpass.getpass(prompt)
    else:
        print(prompt, end="", file=sys.stderr, flush=True)
        value = sys.stdin.readline().strip()
    return value.strip() or current


def cmd_account_add(a):
    """Create or update one instance in the keychain.

    Interactive by default, with secrets read through getpass so they never reach
    the screen, the shell history or argv. Piped JSON is the scripted path — the
    same shape the keychain holds — and replaces the entry whole.
    """
    if not admin.NAME_RE.match(a.name):
        print("Namnet får bara innehålla a–z, 0–9 och bindestreck, t.ex. vartex-outdoor.", file=sys.stderr)
        return 2
    if a.dialog:
        from . import dialog
        old = keychain.get(a.name) or {}
        web = old.get("web") or {}
        flat = {"webshopId": old.get("webshopId"), "baseUrl": old.get("baseUrl") or admin.DEFAULT_BASE_URL,
                "account": old.get("account") or a.name, "key": old.get("key"),
                "email": web.get("email"), "password": web.get("password")}
        got = dialog.ask(a.name, flat)
        if got is None:
            print(f"Avbrutet. Inget sparat för {a.name}.", file=sys.stderr)
            return 1
        # An empty secret field means "keep what is stored", never "erase it".
        for k in ("key", "password"):
            got[k] = got.get(k) or flat[k]
        entry = {"webshopId": got.get("webshopId"), "baseUrl": got.get("baseUrl"),
                 "account": got.get("account"), "key": got.get("key")}
        if got.get("email"):
            entry["web"] = {"email": got["email"], "password": got.get("password")}
    elif not sys.stdin.isatty():
        try:
            entry = json.loads(sys.stdin.read().lstrip("﻿"))
        except ValueError as e:
            print(f"Väntade JSON på stdin: {e}", file=sys.stderr)
            return 2
    else:
        old = keychain.get(a.name) or {}
        web = old.get("web") or {}
        print(f"E37-konto {a.name} ({'uppdateras' if old else 'nytt'}). Enter behåller värdet.", file=sys.stderr)
        entry = {
            "webshopId": _ask("Webbshop-ID", old.get("webshopId")),
            "baseUrl": _ask("API-bas", old.get("baseUrl") or admin.DEFAULT_BASE_URL),
            "account": _ask("Rapport-slug", old.get("account") or a.name),
            "key": _ask("API-nyckel", old.get("key"), secret=True),
        }
        email = _ask("Webbinloggning, e-post", web.get("email"))
        if email:
            entry["web"] = {"email": email, "password": _ask("Webbinloggning, lösenord", web.get("password"), secret=True)}
    entry = {k: v for k, v in entry.items() if v}
    keychain.put(a.name, entry)
    print(f"Sparat {a.name} i {keychain.backend()}.", file=sys.stderr)
    return 0


def cmd_account_remove(a):
    if keychain.delete(a.name):
        print(f"Tog bort {a.name} ur {keychain.backend()}.")
        return 0
    print(f"Inget konto {a.name}.", file=sys.stderr)
    return 1


# ---- order -------------------------------------------------------------------

def _window(a, default):
    if a.start or a.end:
        if not (a.start and a.end):
            raise E37Error("--from och --to anges tillsammans.")
        return a.start, a.end
    return default()


def _resolve_site(session, ref):
    """A site id, or a name (case-insensitive, with or without E37's '(standard)')."""
    if not ref:
        return None
    sites = session.sites()
    clean = [(i, n.replace("(standard)", "").strip()) for i, n in sites]
    for i, n in clean:
        if ref == i or ref.lower() == n.lower():
            return i
    hits = [(i, n) for i, n in clean if ref.lower() in n.lower()]
    if len(hits) == 1:
        return hits[0][0]
    known = ", ".join(f"{n} ({i})" for i, n in (hits or clean))
    raise E37Error(f"{'Flera webbplatser' if hits else 'Ingen webbplats'} matchar {ref!r}: {known}")


def _use_api(acc, a):
    """The API when it can answer and there is a key; otherwise the web login."""
    if getattr(a, "via", None) == "api":
        return True
    if getattr(a, "via", None) == "web":
        return False
    return bool(acc["key"]) and not getattr(a, "site", None)


def cmd_order_flow(a):
    acc = admin.resolve_account(a.account)
    start, end = _window(a, admin.half_hour_window)
    if _use_api(acc, a):
        rows, via = admin.orderflow(acc, start, end, mode=a.mode), "api"
    else:
        s = web.Session(acc)
        rows, via = s.orderflow(start, end, mode=a.mode, site=_resolve_site(s, a.site)), "webb"
    if a.json:
        _dump(rows)
        return 0
    print(f"{acc['name']}  {start:%Y-%m-%d %H:%M} – {end:%Y-%m-%d %H:%M}  ({a.mode}, via {via})  {len(rows)} ordrar\n")
    for r in rows:
        print(f"{r.get('order_id', '?'):>9}  {str(r.get('order_timestamp', ''))[:16]}  "
              f"{float(r.get('total_sum_incl_vat') or 0):>10.2f} {r.get('currency', ''):<3}  "
              f"{r.get('site_name', ''):<20} {r.get('order_status_title', '')}")
    return 0


# ---- report -------------------------------------------------------------------

def _report_type(session, ref):
    types = session.report_types()
    for i, title in types:
        if ref == i:
            return i, title
    hits = [(i, title) for i, title in types if ref.lower() in title.lower()]
    if len(hits) == 1:
        return hits[0]
    raise E37Error(f"{'Flera' if hits else 'Ingen'} rapport matchar {ref!r}. Lista med: e37 report list")


def cmd_report_list(a):
    s = web.Session(admin.resolve_account(a.account))
    types = s.report_types()
    if a.json:
        _dump([{"id": i, "title": t} for i, t in types])
        return 0
    for i, title in types:
        print(f"{i:>6}  {title}")
    return 0


def cmd_report_show(a):
    s = web.Session(admin.resolve_account(a.account))
    rid, title = _report_type(s, a.type)
    settings = s.report_settings(rid)
    if a.json:
        _dump({"id": rid, "title": title, "settings": settings})
        return 0
    print(f"{rid}  {title}\n")
    for st in settings:
        print(f"  {st['id']:<28} {st['kind']:<13} {st['label']}  [standard: {st['default']}]")
        for v, label in st["options"][:40]:
            if v or label:
                print(f"      {v:<10} {label}")
        if len(st["options"]) > 40:
            print(f"      ... {len(st['options']) - 40} till (se --json)")
    return 0


def cmd_report_get(a):
    s = web.Session(admin.resolve_account(a.account))
    rid, title = _report_type(s, a.type)
    settings = {st["id"]: st for st in s.report_settings(rid)}
    values = {}
    for kv in a.set or []:
        if "=" not in kv:
            raise E37Error(f"--set väntar ID=VÄRDE, fick {kv!r}. Se: e37 report show {rid}")
        k, v = kv.split("=", 1)
        if k not in settings:
            raise E37Error(f"Rapport {rid} har ingen inställning {k!r}. Finns: {', '.join(settings)}")
        values[k] = v
    if a.start or a.end:
        start, end = _window(a, None)
        di = next((k for k, st in settings.items() if st["kind"] == "date-interval"), None)
        if not di:
            raise E37Error(f"Rapport {rid} har inget datumintervall.")
        # Each report keeps its own format: some take a time, some only a date.
        fmt = "%Y-%m-%d %H:%M" if ":" in settings[di]["default"] else "%Y-%m-%d"
        values[di] = f"{start.strftime(fmt)},{end.strftime(fmt)}"
    if a.site:
        sk = next((k for k in settings if k.lower() in ("site", "siteid")), None)
        if not sk:
            raise E37Error(f"Rapport {rid} kan inte filtreras på webbplats.")
        values[sk] = _resolve_site(s, a.site)
    data = s.report(rid, values)
    if a.json:
        _dump(data)
        return 0
    rows = data.get("rows", data) if isinstance(data, dict) else data
    print(f"{rid}  {title}: {len(rows)} rader\n")
    if rows:
        cols = list(rows[0].keys())
        print("\t".join(cols))
        for r in rows[:a.top]:
            print("\t".join(str(r.get(c, "")) for c in cols))
        if len(rows) > a.top:
            print(f"... {len(rows) - a.top} rader till (--top N eller --json)")
    return 0


def cmd_sites(a):
    s = web.Session(admin.resolve_account(a.account))
    rows = [{"id": i, "name": n.replace("(standard)", "").strip(), "default": "(standard)" in n}
            for i, n in s.sites()]
    if a.json:
        _dump(rows)
        return 0
    for r in rows:
        print(f"{r['id']:>4}  {r['name']}{'  (standard)' if r['default'] else ''}")
    return 0


def _web_order(acc, order_id):
    o = web.Session(acc).order(order_id)
    if o is None:
        raise E37Error(f"Order {order_id} finns inte hos {acc['name']}, eller syns inte för den här inloggningen.")
    return o


def cmd_order_show(a):
    acc = admin.resolve_account(a.account)
    if _use_api(acc, a):
        o = admin.order(acc, a.id)
        if o is None:
            print(f"Order {a.id} finns inte hos {acc['name']}.", file=sys.stderr)
            return 1
        if a.json:
            _dump(o)
            return 0
        c = o.get("customer") or {}
        print(f"Order {o.get('id')}  {str(o.get('timestamp', ''))[:19]}  {(o.get('site') or {}).get('name', '')}  (via api)")
        print(f"Status:    {(o.get('orderStatus') or {}).get('name', '?')}")
        print(f"ERP:       {o.get('erpOrderNumber') or ('synkad' if o.get('synced') else 'ej synkad')}")
        print(f"Kund:      {c.get('customerNumber', '')}")
        print(f"Betalning: {(o.get('payment') or {}).get('paymentMethod', '')}")
        print(f"Leverans:  {(o.get('delivery') or {}).get('deliveryMethod', '')}")
        print(f"Summa:     {o.get('totalSumInclVat')} {str(o.get('currencyCode', '')).upper()} inkl moms\n")
        for r in o.get("rows") or []:
            # The spec's schema and example disagree on these names; take either.
            name = r.get("name") or r.get("title") or ""
            variant = r.get("variant") or r.get("matrices") or ""
            print(f"  {r.get('quantity', ''):>3} × {r.get('sku', ''):<14} {name} {variant}".rstrip()
                  + f"  {r.get('sumInclVat', '')}")
        return 0
    o = _web_order(acc, a.id)
    if a.json:
        _dump(o)
        return 0
    s = o["summary"]
    print(f"Order {o['order_id']}  {o['order_timestamp']}  {o['site'] or ''}  (via webb)")
    print(f"Orderstatus: {o['order_status']}")
    for k, v in o["other"].items():
        print(f"{k}: {v}")
    print(f"Kund:        {o['customer_number'] or ''} ({o['customer_type'] or ''})")
    print(f"Betalning:   {o['payment']['method'] or ''}  {o['payment']['status'] or ''}")
    print(f"Leverans:    {o['delivery']['method'] or ''}")
    print(f"Summa:       {s.get('Totalt inkl. moms')} inkl moms, {s.get('Moms')} moms\n")
    for r in o["rows"]:
        q = r["quantity"]
        q = int(q) if q is not None and q == int(q) else q
        print(f"  {q if q is not None else '':>3} × {r['sku']:<16} {r['name']}  {r['price_text']}")
    return 0


def cmd_order_status(a):
    acc = admin.resolve_account(a.account)
    if _use_api(acc, a):
        s = admin.order_status(acc, a.id)
        if s is None:
            print(f"Order {a.id} finns inte hos {acc['name']}.", file=sys.stderr)
            return 1
        if a.json:
            _dump(s)
            return 0
        st = s.get("OrderStatus") or {}
        print(f"Order {a.id}: {st.get('Name') or admin.ORDER_STATUS.get(st.get('ID'), '?')} ({st.get('ID')})")
        return 0
    o = _web_order(acc, a.id)
    out = {"order_id": o["order_id"], "order_status": o["order_status"], "payment_status": o["payment"]["status"],
           "site": o["site"], "order_timestamp": o["order_timestamp"], "other": o["other"]}
    if a.json:
        _dump(out)
        return 0
    extra = "  ".join(f"{k}: {v}" for k, v in o["other"].items())
    print(f"Order {a.id}: {o['order_status']}  betalning {o['payment']['status'] or '?'}  {extra}")
    return 0


# ---- shop --------------------------------------------------------------------

def _product_line(p):
    flags = ("" if p.get("in_stock") else " [slut]") + (" [kampanj]" if p.get("is_campaign") else "")
    return f"{p.get('model_number', ''):<14} {p.get('price', ''):>10}  {p.get('name', '')}{flags}"


def cmd_shop_search(a):
    summary, data = shop.search(a.shop, " ".join(a.query), top=a.top, brands=a.brand,
                                sort_by=a.sort, in_stock_only=a.in_stock or None,
                                campaign_only=a.campaign or None)
    if a.json:
        _dump(data)
        return 0
    if summary:
        print(summary + "\n")
    for p in (data or {}).get("products") or []:
        print(_product_line(p))
    return 0


def cmd_shop_product(a):
    if a.gtin:
        p = shop.product(a.shop, gtin=a.id, specifications=a.specs)
    else:
        p = shop.product(a.shop, model_number=a.id, specifications=a.specs)
    if not p:
        print(f"Ingen produkt {a.id}.", file=sys.stderr)
        return 1
    if a.json:
        _dump(p)
        return 0
    print(_product_line(p))
    print(p.get("url", ""))
    for k, v in (p.get("specifications") or {}).items():
        if v is not None:
            print(f"  {k}: {v}")
    if p.get("description"):
        print("\n" + p["description"].strip())
    return 0


def cmd_shop_tools(a):
    rows = shop.tools(a.shop)
    if a.json:
        _dump(rows)
        return 0
    for t in rows:
        props = (t.get("inputSchema") or {}).get("properties") or {}
        args = [k for k in props if k not in ("language_code", "country_code")]
        print(f"{t['name']:<18} {', '.join(args)}")
    return 0


def _cmd_shop_list(tool):
    def run(a):
        data = shop.call(a.shop, tool)[1] or []
        if a.json:
            _dump(data)
            return 0
        for x in data:
            count = f"  ({x['nr_of_products']})" if "nr_of_products" in x else ""
            print(f"{x.get('key') or x.get('name') or x.get('title')}{count}")
            for ch in x.get("children") or []:
                print(f"    {ch.get('key')}")
        return 0
    return run


# ---- skill and update --------------------------------------------------------

REPO = "Wesports-Scandinavia-AB/e37-cli"


def _skill_text():
    from importlib.resources import files
    return files("e37").joinpath("skill/SKILL.md").read_text(encoding="utf-8")


def cmd_skill_show(a):
    print(_skill_text())
    return 0


def cmd_skill_install(a):
    """Put SKILL.md where Claude Code finds it, so later conversations know e37.

    Overwritten on every install: the file comes from this package, and an
    upgrade should bring the instructions along with the code they describe.
    """
    from pathlib import Path
    target = Path(a.dir).expanduser() if a.dir else Path.home() / ".claude" / "skills" / "e37"
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(_skill_text(), encoding="utf-8")
    print(f"Skill installerad: {target / 'SKILL.md'}")
    return 0


def cmd_update(a):
    """Reinstall from GitHub, then refresh the skill with the NEW code.

    --force-reinstall because pip treats a URL whose version did not change as
    already satisfied, and main moves between version bumps. --user only outside
    a virtualenv, where it is refused. The skill step runs in a fresh process so
    it writes the new SKILL.md, not the one this old process has loaded.
    """
    import shutil
    import subprocess
    from . import __version__
    url = (f"git+https://github.com/{REPO}" if shutil.which("git")
           else f"https://github.com/{REPO}/archive/refs/heads/main.zip")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps",
           "--quiet", "--disable-pip-version-check", f"e37-cli @ {url}"]
    if sys.prefix == sys.base_prefix:
        cmd.insert(4, "--user")
    print(f"Hämtar senaste e37-cli (har {__version__}) ...", file=sys.stderr)
    if subprocess.run(cmd).returncode:
        print("Uppdateringen misslyckades, se pip-utskriften ovan.", file=sys.stderr)
        return 1
    new = subprocess.run([sys.executable, "-c", "import e37; print(e37.__version__)"],
                         capture_output=True, text=True).stdout.strip()
    subprocess.run([sys.executable, "-m", "e37", "skill", "install"])
    print(f"e37-cli {__version__} -> {new or '?'}")
    return 0


# ---- wiring ------------------------------------------------------------------

def _parser(sub, name, help, description=None, epilog=None):
    """A subcommand whose --help shows a description and examples, not just flags.

    The reader of --help is as often an assistant deciding what to run as a
    person, so each command says what it reads, what it needs and how to call it.
    """
    return sub.add_parser(name, help=help, description=description or help, epilog=epilog,
                          formatter_class=argparse.RawDescriptionHelpFormatter)


def _json_flag(s):
    s.add_argument("--json", action="store_true",
                   help="machine-readable JSON on stdout instead of the human summary")


def _account_flag(s):
    s.add_argument("--account", metavar="NAME",
                   help="which E37 instance (see `e37 account list`); required when more than one is stored")


def _add_account_commands(sub):
    s = _parser(sub, "list", "list stored E37 instances and which secrets they have",
                "List the E37 instances stored in this user's OS keychain. Shows name, webshop ID,\n"
                "API base and whether an API key and a web login exist. Never prints a secret.",
                "example:\n  e37 account list --json")
    _json_flag(s)
    s.set_defaults(fn=cmd_account_list)

    s = _parser(sub, "add", "add or update one E37 instance (window, prompts or JSON on stdin)",
                "Store or update one E37 instance in the OS keychain (Windows Credential Manager,\n"
                "macOS keychain). Three ways in:\n"
                "  --dialog   a window on this screen; the person types, nothing passes through\n"
                "             a chat or the command line. Use this when you are an assistant.\n"
                "  terminal   prompts, secrets hidden, Enter keeps the current value\n"
                "  stdin      piped JSON, for scripts run by the owner of the secrets only\n"
                "An empty secret field keeps what is stored.",
                "examples:\n  e37 account add vartex-outdoor --dialog\n"
                "  e37 account add vartex-outdoor\n\n"
                "JSON shape on stdin:\n"
                '  {"webshopId": "...", "baseUrl": "https://admin3.e37.se/api", "account": "...",\n'
                '   "key": "...", "web": {"email": "...", "password": "..."}}')
    s.add_argument("name", help="short name for the instance: a-z, 0-9 and hyphens, e.g. vartex-outdoor")
    s.add_argument("--dialog", action="store_true", help="open a window for the values (see above)")
    s.set_defaults(fn=cmd_account_add)

    s = _parser(sub, "remove", "delete one E37 instance from the keychain",
                epilog="example:\n  e37 account remove vartex-outdoor")
    s.add_argument("name")
    s.set_defaults(fn=cmd_account_remove)


def _add_order_commands(sub):
    s = _parser(sub, "flow", "orders completed in a time window (the order flow report)",
                "Orders whose payment was confirmed inside a time window, from E37's order flow\n"
                "report. Read-only. Without --from/--to: the previous closed half hour. Times are\n"
                "Swedish local time. Uses the API when the instance has a key, otherwise the\n"
                "person's own E37 Admin login (which also gives the extra columns).\n\n"
                "JSON: a list of rows with order_id, order_timestamp, total_sum_incl_vat,\n"
                "total_sum_excl_vat, currency, country, country_name, language, person_type,\n"
                "site_id, site_name; via the web also order_status_title, payment_method_title,\n"
                "shipping_fee_incl_vat, erp_import_status, external_marketplace_title and more.",
                "examples:\n  e37 order flow --account vartex-outdoor --json\n"
                "  e37 order flow --account vartex-outdoor --from '2026-10-07 08:00' --to '2026-10-07 12:00' --json\n"
                "  e37 order flow --account vartex-outdoor --site 'Addnature SE' --json")
    _account_flag(s)
    _window_flags(s)
    s.add_argument("--mode", default="completed", choices=("completed", "created"),
                   help="completed (default): when the payment was confirmed; created: when checkout began")
    s.add_argument("--site", metavar="ID|NAME", help="only one site, e.g. 'Addnature SE' or 20 (web login only)")
    s.add_argument("--via", choices=("api", "web"),
                   help="force a route; default is the API when the instance has a key, else the web login")
    _json_flag(s)
    s.set_defaults(fn=cmd_order_flow)

    s = _parser(sub, "show", "one order in full: customer, addresses, payment, delivery, rows",
                "One order. Read-only. Through the API when the instance has a key, otherwise\n"
                "from the order window in E37 Admin via the person's login. Contains personal\n"
                "data (name, e-mail, phone, addresses): show only what the question needs.\n\n"
                "JSON via the web: order_id, order_timestamp, order_status, site, customer_number,\n"
                "customer_type, vat, payment{method,status,invoice_number}, delivery{method,\n"
                "pickup_point}, other (e.g. ERP sync), addresses, contact, rows[{sku, name,\n"
                "quantity, unit_price, sum}], summary{label: amount}, notes.\n"
                "JSON via the API: E37's Order object (see docs/order-api.md).",
                "example:\n  e37 order show 1189437 --account vartex-outdoor --json")
    s.add_argument("id", type=int, help="E37 order number")
    _account_flag(s)
    s.add_argument("--via", choices=("api", "web"), help="force a route; default API with a key, else web")
    _json_flag(s)
    s.set_defaults(fn=cmd_order_show)

    s = _parser(sub, "status", "one order's current status",
                "Current status of one order. Read-only. API when there is a key, else the web:\n"
                "order_status (Mottagen/ny, Levererad, Annullerad, ...), payment_status, ERP sync.",
                "example:\n  e37 order status 1189437 --account vartex-outdoor --json")
    s.add_argument("id", type=int, help="E37 order number")
    _account_flag(s)
    s.add_argument("--via", choices=("api", "web"), help="force a route; default API with a key, else web")
    _json_flag(s)
    s.set_defaults(fn=cmd_order_status)


def _add_shop_commands(sub):
    def shop_arg(s):
        s.add_argument("--shop", help=f"{', '.join(shop.SHOPS)} or a shop's MCP URL "
                                      f"(default $E37_MCP_URL, else {shop.DEFAULT_SHOP})")
        _json_flag(s)

    s = _parser(sub, "search", "search a shop's products: price, stock, campaign, variants",
                "Free-text product search in one E37 shop. No login. Words are OR-ed, so search\n"
                "on one or two keywords ('tält 2P'), not a sentence, and filter the result\n"
                "yourself. price is text ('3 399 kr'). E37's category and tag filters have no\n"
                "effect and are not offered here.\n\n"
                "JSON: products[] with model_number, name, brand, price, currency, in_stock,\n"
                "is_campaign, url, variations[]; plus total counts and facets.",
                "examples:\n  e37 shop search regnjacka --top 5 --in-stock --json\n"
                "  e37 shop search jacka --brand Patagonia --sort price_asc --json\n"
                "  e37 shop search tält --shop outdoorexperten --json")
    s.add_argument("query", nargs="+", help="search words, 2-100 characters in total")
    s.add_argument("--top", type=int, default=30, metavar="N", help="max products (default 30, max 100)")
    s.add_argument("--brand", action="append", metavar="NAME", help="only this brand (exact name), repeatable")
    s.add_argument("--sort", choices=shop.SORT_KEYS, help="order of results (default rank)")
    s.add_argument("--in-stock", action="store_true", help="only products in stock")
    s.add_argument("--campaign", action="store_true", help="only products on campaign")
    shop_arg(s)
    s.set_defaults(fn=cmd_shop_search)

    s = _parser(sub, "product", "one product model by model number (or GTIN)",
                "One product model: name, brand, price, stock, description, and with --specs\n"
                "colour, material, target group, weight. Take model_number from a search.",
                "example:\n  e37 shop product 152668-0073 --specs --json")
    s.add_argument("id", help="model number, e.g. 152668-0073 (or a GTIN with --gtin)")
    s.add_argument("--gtin", action="store_true", help="id is a GTIN for one variant")
    s.add_argument("--specs", action="store_true", help="include specifications")
    shop_arg(s)
    s.set_defaults(fn=cmd_shop_product)

    s = _parser(sub, "tools", "the shop server's own tool list and arguments",
                "What the shop's MCP server itself says it offers. For checking when this tool\n"
                "and the server disagree.")
    shop_arg(s)
    s.set_defaults(fn=cmd_shop_tools)

    for name, tool, text in (("brands", "list_brands", "every brand with product counts"),
                             ("categories", "list_categories", "top level categories"),
                             ("tags", "list_tags", "tags, two levels")):
        s = _parser(sub, name, text, epilog=f"example:\n  e37 shop {name} --json")
        shop_arg(s)
        s.set_defaults(fn=_cmd_shop_list(tool))


def _window_flags(s):
    s.add_argument("--from", dest="start", type=_when, metavar="'YYYY-MM-DD HH:MM'",
                   help="window start, local time")
    s.add_argument("--to", dest="end", type=_when, metavar="'YYYY-MM-DD HH:MM'", help="window end, local time")


def _add_report_commands(sub):
    s = _parser(sub, "list", "the reports E37 Admin offers this login",
                "Every report type in E37 Admin's report page (sales per article or brand, VAT,\n"
                "order events, refunds, stock per brand, gift cards, campaign planning, ...).\n"
                "Needs the instance's web login.",
                "example:\n  e37 report list --account vartex-outdoor --json")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_report_list)

    s = _parser(sub, "show", "the settings one report takes, with their allowed values",
                "The settings of one report: id, kind (date-interval, select, checkbox, radio,\n"
                "text), label, default and allowed values. Use the ids with `report get --set`.",
                "example:\n  e37 report show 21 --account vartex-outdoor --json\n"
                "  e37 report show varumärken --account vartex-outdoor")
    s.add_argument("type", help="report id or part of its title")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_report_show)

    s = _parser(sub, "get", "run one report and get its rows",
                "Run one report as JSON through the person's E37 Admin login. Read-only.\n"
                "--from/--to fill the report's date interval in the format it uses; --site its\n"
                "site filter; anything else with --set ID=VALUE (ids from `report show`).\n"
                "Settings not given keep E37's defaults; checkboxes default to off.\n\n"
                "JSON: {\"rows\": [...], \"columns\": [...]} as E37 delivers it.",
                "examples:\n  e37 report get 21 --account vartex-outdoor --from '2026-10-01 00:00' --to '2026-10-07 23:59' --json\n"
                "  e37 report get 7 --account vartex-outdoor --site 'Addnature SE' --set personType=1 --json")
    s.add_argument("type", help="report id or part of its title")
    _account_flag(s)
    _window_flags(s)
    s.add_argument("--site", metavar="ID|NAME", help="only one site")
    s.add_argument("--set", action="append", metavar="ID=VALUE", help="any other setting, repeatable")
    s.add_argument("--top", type=int, default=20, metavar="N", help="rows shown without --json (default 20)")
    _json_flag(s)
    s.set_defaults(fn=cmd_report_get)


def _add_skill_commands(sub):
    s = _parser(sub, "install", "install the Claude skill that teaches Claude to use e37",
                "Write SKILL.md to ~/.claude/skills/e37/, where Claude Code (and Code in the\n"
                "Claude app) loads it in every conversation. `e37 update` does this for you.",
                "example:\n  e37 skill install")
    s.add_argument("--dir", help="install somewhere else, e.g. a project's .claude/skills/e37")
    s.set_defaults(fn=cmd_skill_install)
    s = _parser(sub, "show", "print the skill: how an assistant should use e37")
    s.set_defaults(fn=cmd_skill_show)


def main(argv=None):
    from . import __version__
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(
        prog="e37",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Read orders and products out of the E37 webshop platform. Nothing here writes to E37.\n\n"
                    "  shop     products in a shop, no login needed\n"
                    "  order    orders: the API with a key, otherwise your own E37 Admin login\n"
                    "  report   any E37 Admin report as JSON, via your own login\n"
                    "  sites    the shops your login can see\n"
                    "  account  your E37 instances, stored in the OS keychain\n"
                    "  skill    teach Claude how to use this tool\n"
                    "  update   get the latest version from GitHub",
        epilog="If you are an assistant: run `e37 skill show` for how to use this tool, and never\n"
               "ask for a password or API key in the chat; use `e37 account add NAME --dialog`.\n"
               "Every command has --help with examples.",
    )
    p.add_argument("--version", action="version", version=f"e37-cli {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{shop,order,report,sites,account,skill,update}")

    sh = _parser(sub, "shop", "products in a shop: search, product, brands, categories, tags")
    _add_shop_commands(sh.add_subparsers(dest="shop_cmd", required=True))

    o = _parser(sub, "order", "orders from E37 Admin: flow, show, status (read-only)")
    _add_order_commands(o.add_subparsers(dest="order_cmd", required=True))

    r = _parser(sub, "report", "any E37 Admin report as JSON: list, show, get (web login)")
    _add_report_commands(r.add_subparsers(dest="report_cmd", required=True))

    s = _parser(sub, "sites", "the sites (shops) an instance's web login can see",
                epilog="example:\n  e37 sites --account vartex-outdoor --json")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_sites)

    ac = _parser(sub, "account", "your E37 instances in the OS keychain: list, add, remove")
    _add_account_commands(ac.add_subparsers(dest="account_cmd", required=True))

    sk = _parser(sub, "skill", "the Claude skill for e37: install, show")
    _add_skill_commands(sk.add_subparsers(dest="skill_cmd", required=True))

    s = _parser(sub, "update", "get the latest e37-cli from GitHub and refresh the Claude skill",
                "Reinstall e37-cli from GitHub for this Python and rewrite the Claude skill.\n"
                "Accounts in the keychain are kept.",
                "example:\n  python -m e37 update")
    s.set_defaults(fn=cmd_update)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except E37Error as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
