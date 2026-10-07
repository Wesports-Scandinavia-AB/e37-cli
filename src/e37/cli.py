import argparse
import json
import sys
from datetime import datetime

from . import E37Error, admin, shop


def _dump(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _when(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError(f"väntade 'ÅÅÅÅ-MM-DD TT:MM', fick {s!r}")


# ---- accounts ----------------------------------------------------------------

def cmd_accounts(a):
    rows = admin.accounts()
    if a.json:
        _dump([{k: v for k, v in r.items() if k != "key"} for r in rows])
        return 0
    print(f"konfiguration  {admin.config_path()}\n")
    for r in rows:
        print(f"{r['name']:<16} account={r['account']:<16} webshopId={r['webshopId'] or '-':<8} {r['baseUrl']}")
    return 0


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

    s = sub.add_parser("accounts", help="the configured shops (never the key)")
    _json_flag(s)
    s.set_defaults(fn=cmd_accounts)

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
