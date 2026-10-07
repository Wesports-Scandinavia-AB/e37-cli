import argparse
import json
import sys
from datetime import datetime

from . import E37Error, admin, keychain, shop


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
    if not sys.stdin.isatty():
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

def cmd_order_flow(a):
    acc = admin.resolve_account(a.account)
    if a.start or a.end:
        if not (a.start and a.end):
            print("--from och --to anges tillsammans.", file=sys.stderr)
            return 2
        start, end = a.start, a.end
    else:
        start, end = admin.half_hour_window()
    rows = admin.orderflow(acc, start, end, mode=a.mode)
    if a.json:
        _dump(rows)
        return 0
    print(f"{acc['name']}  {start:%Y-%m-%d %H:%M} – {end:%H:%M}  ({a.mode})  {len(rows)} ordrar\n")
    for r in rows:
        print(f"{r.get('order_id', '?'):>9}  {str(r.get('order_timestamp', ''))[:19]}  "
              f"{r.get('total_sum_incl_vat', 0):>10.2f} {r.get('currency', ''):<3}  "
              f"{r.get('site_name', '')}")
    return 0


def cmd_order_show(a):
    acc = admin.resolve_account(a.account)
    o = admin.order(acc, a.id)
    if o is None:
        print(f"Order {a.id} finns inte hos {acc['name']}.", file=sys.stderr)
        return 1
    if a.json:
        _dump(o)
        return 0
    c = o.get("customer") or {}
    print(f"Order {o.get('id')}  {str(o.get('timestamp', ''))[:19]}  {(o.get('site') or {}).get('name', '')}")
    print(f"Status:   {(o.get('orderStatus') or {}).get('name', '?')}")
    print(f"ERP:      {o.get('erpOrderNumber') or ('synkad' if o.get('synced') else 'ej synkad')}")
    print(f"Kund:     {c.get('customerNumber', '')} {c.get('email', '')}")
    print(f"Betalning: {(o.get('payment') or {}).get('paymentMethod', '')}")
    print(f"Leverans: {(o.get('delivery') or {}).get('deliveryMethod', '')}")
    print(f"Summa:    {o.get('totalSumInclVat')} {str(o.get('currencyCode', '')).upper()} inkl moms\n")
    for r in o.get("rows") or []:
        # The spec's schema and example disagree on these names; take either.
        name = r.get("name") or r.get("title") or ""
        variant = r.get("variant") or r.get("matrices") or ""
        print(f"  {r.get('quantity', ''):>3} × {r.get('sku', ''):<14} {name} {variant}".rstrip()
              + f"  {r.get('sumInclVat', '')}")
    return 0


def cmd_order_status(a):
    acc = admin.resolve_account(a.account)
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


# ---- wiring ------------------------------------------------------------------

def _json_flag(s):
    s.add_argument("--json", action="store_true", help="raw JSON instead of the summary")


def _add_order_commands(sub):
    s = sub.add_parser("flow", help="the order flow report: orders completed in a window")
    s.add_argument("--account", help="which configured shop (needed when there are several)")
    s.add_argument("--from", dest="start", type=_when, metavar="'ÅÅÅÅ-MM-DD TT:MM'",
                   help="window start, local time (default: the previous closed half hour)")
    s.add_argument("--to", dest="end", type=_when, metavar="'ÅÅÅÅ-MM-DD TT:MM'", help="window end")
    s.add_argument("--mode", default="completed", help="orderTimestampMode (default completed)")
    _json_flag(s)
    s.set_defaults(fn=cmd_order_flow)

    s = sub.add_parser("show", help="one order in full: customer, payment, delivery, rows")
    s.add_argument("id", type=int)
    s.add_argument("--account")
    _json_flag(s)
    s.set_defaults(fn=cmd_order_show)

    s = sub.add_parser("status", help="one order's current status")
    s.add_argument("id", type=int)
    s.add_argument("--account")
    _json_flag(s)
    s.set_defaults(fn=cmd_order_status)


def _add_shop_commands(sub):
    def shop_arg(s):
        s.add_argument("--shop", help=f"{', '.join(shop.SHOPS)} or an MCP URL "
                                      f"(default $E37_MCP_URL, else {shop.DEFAULT_SHOP})")
        _json_flag(s)

    s = sub.add_parser("search", help="search products")
    s.add_argument("query", nargs="+")
    s.add_argument("--top", type=int, default=30, metavar="N", help="max products (default 30)")
    s.add_argument("--brand", action="append", help="filter on brand name, repeatable")
    s.add_argument("--sort", choices=shop.SORT_KEYS)
    s.add_argument("--in-stock", action="store_true")
    s.add_argument("--campaign", action="store_true")
    shop_arg(s)
    s.set_defaults(fn=cmd_shop_search)

    s = sub.add_parser("product", help="one product model by model number (or --gtin)")
    s.add_argument("id", help="model number, e.g. 152668-0073")
    s.add_argument("--gtin", action="store_true", help="id is a GTIN for one variant instead")
    s.add_argument("--specs", action="store_true", help="include specifications")
    shop_arg(s)
    s.set_defaults(fn=cmd_shop_product)

    s = sub.add_parser("tools", help="the server's own tool list, for when docs/mcp.md drifts")
    shop_arg(s)
    s.set_defaults(fn=cmd_shop_tools)

    for name, tool, text in (("brands", "list_brands", "every brand with product counts"),
                             ("categories", "list_categories", "top level categories"),
                             ("tags", "list_tags", "tags, two levels")):
        s = sub.add_parser(name, help=text)
        shop_arg(s)
        s.set_defaults(fn=_cmd_shop_list(tool))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(
        prog="e37",
        description="Orders and products out of E37. "
                    "order: E37 Admin (API key), shop: the shop's public MCP (no key).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ac = sub.add_parser("account", help="E37 instances in your OS keychain (personal logins)")
    acs = ac.add_subparsers(dest="account_cmd", required=True)
    s = acs.add_parser("list", help="instances and which secrets they have (never the values)")
    _json_flag(s)
    s.set_defaults(fn=cmd_account_list)
    s = acs.add_parser("add", help="create or update one, prompts; or pipe JSON on stdin")
    s.add_argument("name", help="your name for the instance, e.g. vartex-outdoor")
    s.set_defaults(fn=cmd_account_add)
    s = acs.add_parser("remove", help="delete one from the keychain")
    s.add_argument("name")
    s.set_defaults(fn=cmd_account_remove)

    o = sub.add_parser("order", help="E37 Admin: order flow report and the REST API")
    _add_order_commands(o.add_subparsers(dest="order_cmd", required=True))

    sh = sub.add_parser("shop", help="the shop's public MCP: products, brands, categories, tags")
    _add_shop_commands(sh.add_subparsers(dest="shop_cmd", required=True))

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except E37Error as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
