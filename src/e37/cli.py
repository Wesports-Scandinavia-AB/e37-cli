import argparse
import json
import sys
from datetime import datetime

from . import E37Error, admin, attributes, keychain, registers, shop, web


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


# ---- view (campaigns, discount codes, tags, ... read-only) --------------------

def _first_line(s):
    return next((x.strip() for x in s.splitlines() if x.strip()), "")


def cmd_view(a):
    s = web.Session(admin.resolve_account(a.account))
    if a.site:
        s.switch_site(_resolve_site(s, a.site))
    if a.ref is None:
        rows = registers.items(s, a.kind)
        if a.find:
            q = a.find.lower()
            rows = [r for r in rows if q in " ".join([r["name"], *r["columns"], *r["notes"], r["parent"] or ""]).lower()]
        if a.json:
            _dump(rows)
            return 0
        section = object()
        for r in rows:
            if r["section"] != section and r["section"]:
                print(f"\n{r['section']}")
            section = r["section"]
            name = f"{r['parent']} › {r['name']}" if r["parent"] else r["name"]
            extra = "  ".join(r["columns"] + [_first_line(n) for n in r["notes"][:1]])
            print(f"{r['id']:>7}  {name}{'  · ' + extra if extra else ''}")
        print(f"\n{len(rows)} st i {registers.REGISTERS[a.kind][1]}")
        return 0
    d = registers.item(s, a.kind, a.ref)
    if a.json:
        _dump(d)
        return 0
    print(f"{d['title']}  (id {d['id']})")
    tab = None
    for f in d["fields"]:
        if f["tab"] != tab:
            print(f"\n  {f['tab']}")
            tab = f["tab"]
        print(f"    {f['label']}: {f['value']}")
    for lst in d["lists"]:
        print(f"\n  {lst['tab']}{' – ' + lst['label'] if lst['label'] else ''} ({len(lst['items'])} st)")
        for i, it in enumerate(lst["items"][:a.top], 1):
            note = "  ⚠ " + " / ".join(_first_line(n) for n in it["notes"]) if it.get("notes") else ""
            print(f"    {i:>3}. {it['text']}{note}")
        if len(lst["items"]) > a.top:
            print(f"    … {len(lst['items']) - a.top} till (--top N eller --json)")
    return 0


def cmd_change(a):
    """Dry run unless --apply. Every change is logged with the old value, so it can be undone."""
    acc = admin.resolve_account(a.account)
    s = web.Session(acc)
    site = None
    if a.site:
        site = _resolve_site(s, a.site)
        s.switch_site(site)
    sets = []
    for spec in a.set or []:
        if "=" not in spec:
            raise E37Error(f"--set väntar FÄLT=VÄRDE, fick {spec!r}")
        key, value = spec.split("=", 1)
        sets.append((key.strip(), value))
    copy = getattr(a, "copy", False)
    if not sets and not copy:
        raise E37Error(f"Ange minst ett --set 'Fält=värde'. Fälten syns med: e37 view {a.kind} {a.ref}")
    site_name = dict(s.sites()).get(site or s.current_site(), "")
    log = a.log or (f"e37-{'kopia' if copy else 'andring'}-{datetime.now():%Y%m%d-%H%M%S}"
                    f"{'' if a.apply else '-torr'}.csv")
    rows, error, r = [], None, None
    done, would = ("skapad", "skulle skapas") if copy else ("ändrad", "skulle ändras")
    try:
        r = registers.change(s, a.kind, a.ref, sets, apply=a.apply, copy=copy)
        for c in r["changes"]:
            rows.append({"konto": acc["name"], "webbplats": site_name, "sort": a.kind, "id": r["id"],
                         "namn": r["name"], "fält": c["label"], "gammalt": c["old"], "nytt": c["new"],
                         "status": done if r["saved"] else would})
    except E37Error as e:
        error = e
        rows.append({"konto": acc["name"], "webbplats": site_name, "sort": a.kind, "id": a.ref, "namn": "",
                     "fält": "; ".join(k for k, _ in sets), "gammalt": "", "nytt": "", "status": f"FEL: {e}"})
    path = _write_log(log, rows, ("konto", "webbplats", "sort", "id", "namn", "fält", "gammalt", "nytt", "status"))
    created = {"id": r["id"], "name": r["name"]} if copy and r and r["saved"] else None
    if a.json:
        _dump({"apply": a.apply, "log": str(path), "rows": rows, **({"created": created} if copy else {})})
        return 1 if error else 0
    print(f"{acc['name']}  {registers.REGISTERS[a.kind][1]} {a.ref}{' (kopia)' if copy else ''}"
          f"{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}")
    for row in rows:
        print(f"  {row['status']}" if row["status"].startswith("FEL")
              else f"  {row['fält']}: {row['gammalt']!r} -> {row['nytt']!r}  ({row['status']})")
    if not rows:
        print("  Kopian får samma värden som originalet." if copy else "  Inget att ändra: fälten har redan de värdena.")
    if created:
        print(f"  Ny post: {created['name']} (id {created['id']})")
    print(f"Logg: {path}", file=sys.stderr)
    return 1 if error else 0


def _web_on_site(a):
    acc = admin.resolve_account(a.account)
    s = web.Session(acc)
    if a.site:
        s.switch_site(_resolve_site(s, a.site))
    return acc, s


def cmd_additions_check(a):
    acc, s = _web_on_site(a)
    site = dict(s.sites()).get(s.current_site(), "")

    def progress(k, n, name):
        if not a.json:
            print(f"\r  {k}/{n} {name[:50]:<50}", end="", file=sys.stderr, flush=True)
    rows = registers.unbuyable(s, sets=a.set, progress=progress)
    if not a.json:
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
    if a.json:
        _dump({"site": site, "rows": rows})
        return 0
    print(f"{acc['name']}  {site}: {len(rows)} tillval med varning\n")
    current = None
    for r in rows:
        if r["set"] != current:
            print(f"{r['set_id']:>5}  {r['set']}")
            current = r["set"]
        print(f"       {r['position']:>2}. {r['art_nr']:<14} {r['text'].split(', ', 2)[-1][:40]:<40}  "
              f"⚠ {_first_line(r['notes'][0])}")
    return 0


def cmd_additions_swap(a):
    acc, s = _web_on_site(a)
    site = dict(s.sites()).get(s.current_site(), "")
    log = a.log or f"e37-tillval-{datetime.now():%Y%m%d-%H%M%S}{'' if a.apply else '-torr'}.csv"
    rec = {"konto": acc["name"], "webbplats": site, "uppsättning": a.set, "plats": "",
           "gammalt": a.old, "nytt": a.new, "status": ""}
    error = None
    try:
        r = registers.swap_addition(s, a.set, a.old, a.new, apply=a.apply)
        rec.update(uppsättning=f"{r['set']} ({r['set_id']})", plats=r["position"], gammalt=r["old"], nytt=r["new"],
                   status="bytt" if r["saved"] else "skulle bytas")
    except E37Error as e:
        error = e
        rec["status"] = f"FEL: {e}"
    path = _write_log(log, [rec], ("konto", "webbplats", "uppsättning", "plats", "gammalt", "nytt", "status"))
    if a.json:
        _dump({"apply": a.apply, "log": str(path), **rec})
    else:
        print(f"{acc['name']}  {rec['uppsättning']}{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}")
        print(f"  {rec['status']}" if error else f"  plats {rec['plats']}: {rec['gammalt']} -> {rec['nytt']}  ({rec['status']})")
        print(f"Logg: {path}", file=sys.stderr)
    return 1 if error else 0


def _cmd_tag(remove):
    def run(a):
        a.limit = None
        acc, s = _web_on_site(a)
        arts = [x for x, _ in _articles_from(a)]
        log = a.log or f"e37-tagg-{datetime.now():%Y%m%d-%H%M%S}{'' if a.apply else '-torr'}.csv"
        rows, error = [], None
        try:
            r = registers.tag_articles(s, a.tag, arts, remove=remove, apply=a.apply)
            status = (("borttagen" if remove else "tillagd") if r["saved"]
                      else ("skulle tas bort" if remove else "skulle läggas till"))
            rows = [{"konto": acc["name"], "tagg": r["tag"], "artikel": x, "åtgärd": "ta bort" if remove else "lägg till",
                     "status": status} for x in r["change"]]
            rows += [{"konto": acc["name"], "tagg": r["tag"], "artikel": x, "åtgärd": "", "status": "oförändrad"}
                     for x in r["unchanged"]]
        except E37Error as e:
            error = e
            rows.append({"konto": acc["name"], "tagg": a.tag, "artikel": ", ".join(arts[:20]),
                         "åtgärd": "ta bort" if remove else "lägg till", "status": f"FEL: {e}"})
        path = _write_log(log, rows, ("konto", "tagg", "artikel", "åtgärd", "status"))
        if a.json:
            _dump({"apply": a.apply, "log": str(path), "rows": rows})
            return 1 if error else 0
        print(f"{acc['name']}  tagg {rows[0]['tagg'] if rows else a.tag}"
              f"{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}")
        for r in rows:
            print(f"  {r['status']}" if r["status"].startswith("FEL") else f"  {r['artikel']:<50} {r['status']}")
        print(f"Logg: {path}", file=sys.stderr)
        return 1 if error else 0
    return run


def cmd_matrix_values(a):
    acc, s = _web_on_site(a)
    vals = registers.matrix_values(s, a.matrix)
    if a.find:
        vals = [(i, v) for i, v in vals if a.find.lower() in v.lower()]
    if a.json:
        _dump([{"position": n, "id": i, "value": v} for n, (i, v) in enumerate(vals, 1)])
        return 0
    for n, (i, v) in enumerate(vals, 1):
        print(f"{n:>5}  {v}")
    return 0


def cmd_matrix_sort(a):
    acc, s = _web_on_site(a)
    wanted = [w.strip() for w in a.order.split(",") if w.strip()]
    log = a.log or f"e37-sortering-{datetime.now():%Y%m%d-%H%M%S}{'' if a.apply else '-torr'}.csv"
    site = dict(s.sites()).get(s.current_site(), "")
    error = None
    try:
        r = registers.sort_matrix(s, a.matrix, wanted, apply=a.apply)
        status = "sorterad" if r["saved"] else ("oförändrad" if r["before"] == r["after"] else "skulle sorteras")
        rec = {"konto": acc["name"], "webbplats": site, "matris": r["matrix"],
               "gammalt": ",".join(r["before"]), "nytt": ",".join(r["after"]), "status": status}
    except E37Error as e:
        error = e
        r = None
        rec = {"konto": acc["name"], "webbplats": site, "matris": a.matrix, "gammalt": "", "nytt": a.order,
               "status": f"FEL: {e}"}
    path = _write_log(log, [rec], ("konto", "webbplats", "matris", "gammalt", "nytt", "status"))
    if a.json:
        _dump({"apply": a.apply, "log": str(path), **rec})
        return 1 if error else 0
    print(f"{acc['name']}  {rec['matris']}  {site}{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}")
    if error:
        print(f"  {rec['status']}")
    else:
        moved = [n for n, (b, f) in enumerate(zip(r["before"], r["after"]), 1) if b != f]
        for n in moved[:40]:
            print(f"  {n:>5}  {r['before'][n - 1]:<20} -> {r['after'][n - 1]}")
        print(f"  {len(moved)} platser ändras ({status})" if moved else "  redan i den ordningen")
    print(f"Logg: {path}", file=sys.stderr)
    return 1 if error else 0


def cmd_page_show(a):
    acc, s = _web_on_site(a)
    p = registers.page(s, a.page, version=a.version)
    if a.json:
        _dump(p)
        return 0
    print(f"{p['name']}  (id {p['id']})")
    if p["versions"]:
        print("\n  Versioner")
        for v in p["versions"]:
            print(f"    {v['id']:>6}  {v['from'] or '':<16} – {v['to'] or '':<16}  {v['title']}")
    print(f"\n  Widgetar{' i version ' + str(a.version) if a.version else ''}")
    for w in p["widgets"]:
        print(f"    {w['id']:>7}  {w['type']:<28} {w['title']}")
    return 0


def cmd_page_widget(a):
    acc, s = _web_on_site(a)
    w = registers.widget(s, a.page, a.widget)
    if a.json:
        _dump(w)
        return 0
    print(f"{w['page']}  widget {w['id']}")
    tab = None
    for f in w["fields"]:
        if f["tab"] != tab:
            print(f"\n  {f['tab']}")
            tab = f["tab"]
        print(f"    {f['label']}: {f['value']}")
    return 0


def cmd_page_change(a):
    acc, s = _web_on_site(a)
    sets = []
    for spec in a.set or []:
        if "=" not in spec:
            raise E37Error(f"--set väntar FÄLT=VÄRDE, fick {spec!r}")
        key, value = spec.split("=", 1)
        sets.append((key.strip(), value))
    if not sets:
        raise E37Error(f"Ange minst ett --set 'Fält=värde'. Fälten syns med: e37 page widget {a.page} {a.widget}")
    site = dict(s.sites()).get(s.current_site(), "")
    log = a.log or f"e37-widget-{datetime.now():%Y%m%d-%H%M%S}{'' if a.apply else '-torr'}.csv"
    rows, error = [], None
    try:
        r = registers.change_widget(s, a.page, a.widget, sets, apply=a.apply)
        rows = [{"konto": acc["name"], "webbplats": site, "sida": r["page"], "widget": r["id"], "fält": c["label"],
                 "gammalt": c["old"], "nytt": c["new"], "status": "ändrad" if r["saved"] else "skulle ändras"}
                for c in r["changes"]]
    except E37Error as e:
        error = e
        rows = [{"konto": acc["name"], "webbplats": site, "sida": a.page, "widget": a.widget,
                 "fält": "; ".join(k for k, _ in sets), "gammalt": "", "nytt": "", "status": f"FEL: {e}"}]
    path = _write_log(log, rows, ("konto", "webbplats", "sida", "widget", "fält", "gammalt", "nytt", "status"))
    if a.json:
        _dump({"apply": a.apply, "log": str(path), "rows": rows})
        return 1 if error else 0
    print(f"{acc['name']}  sida {a.page}, widget {a.widget}"
          f"{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}")
    for row in rows:
        print(f"  {row['status']}" if row["status"].startswith("FEL")
              else f"  {row['fält']}: {row['gammalt']!r} -> {row['nytt']!r}  ({row['status']})")
    if not rows:
        print("  Inget att ändra: fälten har redan de värdena.")
    print(f"Logg: {path}", file=sys.stderr)
    return 1 if error else 0


def _campaign_attr(s):
    """The id of the attribute with import key #CAMPAIGN on this instance."""
    hits = [a for a in registers.items(s, "attributes") if a["columns"] and a["columns"][0] == "#CAMPAIGN"]
    if len(hits) != 1:
        raise E37Error("hittade inte kampanjattributet (#CAMPAIGN) bland artikelattributen")
    return hits[0]["id"]


def cmd_campaign_show(a):
    a.limit = None
    acc, s = _web_on_site(a)
    attr = _campaign_attr(s)
    _, vals = attributes.values(s, attr)
    rows = []
    for art, _ in _articles_from(a):
        for v, main in attributes.variants(s, art).items():
            rows.append({"variant": v, "main": main, "values": vals.get(v, {}).get("values", [])})
    if a.json:
        _dump(rows)
        return 0
    for r in rows:
        print(f"  {r['variant']:<16} {', '.join(r['values']) or '–'}")
    return 0


def _cmd_campaign(remove):
    def run(a):
        a.limit = None
        acc, s = _web_on_site(a)
        attr = _campaign_attr(s)
        value = a.value.strip()
        _, vals = attributes.values(s, attr)
        changes, mains = {}, {}
        for art, _ in _articles_from(a):
            for v, main in attributes.variants(s, art).items():
                old = vals.get(v, {}).get("values", [])
                mains[v] = main
                if remove:
                    new = [x for x in old if x.lower() != value.lower()]
                else:
                    new = old if any(x.lower() == value.lower() for x in old) else old + [value]
                changes[v] = new
        log = a.log or f"e37-kampanj-{datetime.now():%Y%m%d-%H%M%S}{'' if a.apply else '-torr'}.csv"
        rows, error = [], None
        try:
            plan, saved = attributes.set_values(s, attr, changes, apply=a.apply, update_tags=a.update_tags)
            changed = {p["variant"] for p in plan}
            for p in plan:
                rows.append({"konto": acc["name"], "huvudartikel": mains.get(p["variant"], ""), "variant": p["variant"],
                             "gammalt": "|".join(p["old"]), "nytt": "|".join(p["new"]),
                             "status": "ändrad" if saved else "skulle ändras"})
            for v in changes:
                if v not in changed:
                    rows.append({"konto": acc["name"], "huvudartikel": mains[v], "variant": v,
                                 "gammalt": "|".join(vals.get(v, {}).get("values", [])), "nytt": "",
                                 "status": "oförändrad"})
        except E37Error as e:
            error = e
            rows.append({"konto": acc["name"], "huvudartikel": "", "variant": ", ".join(list(changes)[:20]),
                         "gammalt": "", "nytt": "", "status": f"FEL: {e}"})
        path = _write_log(log, rows, ("konto", "huvudartikel", "variant", "gammalt", "nytt", "status"))
        if a.json:
            _dump({"apply": a.apply, "log": str(path), "rows": rows})
            return 1 if error else 0
        print(f"{acc['name']}  kampanj {value}: {'ta bort' if remove else 'lägg till'}"
              f"{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}")
        for r in rows:
            print(f"  {r['status']}" if r["status"].startswith("FEL")
                  else f"  {r['variant']:<16} {r['gammalt'] or '–'} -> {r['nytt'] or '–'}  ({r['status']})")
        if a.apply and not error and not a.update_tags:
            print("  Kampanjtaggen och produktlistorna följer efter E37:s nästa synk eller nattjobb "
                  "(--update-tags gör det direkt, men tar tid).")
        print(f"Logg: {path}", file=sys.stderr)
        return 1 if error else 0
    return run


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


# ---- delivery text -------------------------------------------------------------

def _articles_from(a):
    arts = [(x, None) for x in (a.articles or [])]
    if a.file:
        from . import tables
        arts += tables.article_rows(a.file)
    if not arts:
        raise E37Error("Ange artikelnummer eller --file med kolumnen art-nr.")
    return arts[:a.limit] if a.limit else arts


def _sites_from(s, a):
    if not a.site:
        raise E37Error("Ange minst en --site (namn eller id). Lista med: e37 sites --account NAMN")
    out = []
    for ref in a.site:
        sid = _resolve_site(s, ref)
        name = dict(s.sites())[sid].replace("(standard)", "").strip()
        out.append((sid, name))
    return out


def _write_log(path, rows, fields=("konto", "webbplats", "art_nr", "gammalt", "nytt", "status")):
    import csv
    from pathlib import Path
    p = Path(path)
    with p.open("w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Excel opens it right
        w = csv.DictWriter(f, fieldnames=list(fields), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return p.resolve()


def cmd_delivery_get(a):
    acc = admin.resolve_account(a.account)
    s = web.Session(acc)
    arts = _articles_from(a)
    out = []
    for sid, sname in _sites_from(s, a):
        s.switch_site(sid)
        for art, _ in arts:
            rec = {"konto": acc["name"], "webbplats": sname, "art_nr": art, "gammalt": "", "nytt": "", "status": ""}
            try:
                _, lang, value = s.delivery_text(art)
                rec.update(gammalt=value, status=f"ok ({lang})")
            except E37Error as e:
                rec["status"] = f"FEL: {e}"
            out.append(rec)
            if not a.json:
                print(f"{sname:<22} {art:<16} {rec['gammalt']!r}  {'' if rec['status'].startswith('ok') else rec['status']}")
    if a.csv:
        print(f"Sparat: {_write_log(a.csv, out)}", file=sys.stderr)
    if a.json:
        _dump([{"site": r["webbplats"], "art_nr": r["art_nr"], "text": r["gammalt"], "status": r["status"]} for r in out])
    return 1 if any(r["status"].startswith("FEL") for r in out) else 0


def cmd_delivery_set(a):
    """Dry run unless --apply. One article failing is logged and the run goes on;
    other fields changing on save stops everything at once."""
    from datetime import datetime
    acc = admin.resolve_account(a.account)
    s = web.Session(acc)
    arts = _articles_from(a)
    sites = _sites_from(s, a)
    per_site = {}
    for spec in a.site_text or []:
        if "=" not in spec:
            raise E37Error(f"--site-text väntar WEBBPLATS=TEXT, fick {spec!r}")
        ref, tmpl = spec.split("=", 1)
        per_site[_resolve_site(s, ref)] = tmpl
    if a.text is None and not all(sid in per_site for sid, _ in sites):
        raise E37Error("Ange --text 'Förväntas åter i lager: {date}', eller --site-text per webbplats.")
    log = a.log or f"e37-leveranstid-{datetime.now():%Y%m%d-%H%M%S}{'' if a.apply else '-torr'}.csv"

    # The text belongs to the site's LANGUAGE, not the site: every Swedish site shows
    # the same field (verified 2026-10-08). Find each site's language first, and refuse
    # two sites of one language with different texts before anything is written.
    lang_of, first_site = {}, {}
    for sid, sname in sites:
        s.switch_site(sid)
        _, lang, _ = s.delivery_text(arts[0][0])
        lang_of[sid] = lang
        tmpl = per_site.get(sid, a.text)
        if lang in first_site and per_site.get(first_site[lang][0], a.text) != tmpl:
            raise E37Error(f"{sname} och {first_site[lang][1]} delar språk ({lang}) och därmed samma fält, "
                           f"men har olika text. Välj en av dem, eller samma text.")
        first_site.setdefault(lang, (sid, sname))
    out, stop = [], None
    print(f"{len(arts)} artiklar × {len(sites)} webbplatser på {acc['name']}"
          f"{'' if a.apply else '  (TORRKÖRNING, inget sparas; lägg till --apply)'}", file=sys.stderr)
    for sid, sname in sites:
        if stop:
            break
        s.switch_site(sid)
        tmpl = per_site.get(sid, a.text)
        owner = first_site[lang_of[sid]]
        for art, d in arts:
            rec = {"konto": acc["name"], "webbplats": sname, "art_nr": art, "gammalt": "", "nytt": "", "status": ""}
            if owner[0] != sid:
                rec.update(nytt=tmpl.replace("{date}", d or ""), status=f"samma fält som {owner[1]} ({lang_of[sid]})")
                out.append(rec)
                print(f"  {sname:<22} {art:<16} {rec['status']}")
                continue
            try:
                if "{date}" in tmpl and not d:
                    raise E37Error("datum saknas för artikeln, och texten innehåller {date}")
                new = tmpl.replace("{date}", d or "")
                rec["nytt"] = new
                if a.apply:
                    old, now = s.set_delivery_text(art, new, sid)
                    rec["gammalt"] = old
                    rec["status"] = "oförändrad" if old == new else ("ändrad" if now == new else f"FEL: sparat värde är {now!r}")
                else:
                    _, _, old = s.delivery_text(art)
                    rec["gammalt"] = old
                    rec["status"] = "oförändrad" if old == new else "skulle ändras"
            except E37Error as e:
                rec["status"] = f"FEL: {e}"
                if "ANDRA FÄLT" in str(e) or "fel webbplats" in str(e):
                    stop = e
            out.append(rec)
            print(f"  {sname:<22} {art:<16} {rec['status']:<14} {rec['gammalt']!r} -> {rec['nytt']!r}")
            if stop:
                break
    path = _write_log(log, out)
    errors = [r for r in out if r["status"].startswith("FEL")]
    print(f"\nKlart. {len(out) - len(errors)} OK, {len(errors)} fel. Logg: {path}", file=sys.stderr)
    if stop:
        print(f"STOPPADE: {stop}", file=sys.stderr)
    return 1 if errors else 0


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


def _add_delivery_commands(sub):
    def common(s):
        s.add_argument("articles", nargs="*", metavar="ART", help="exact variant article numbers")
        s.add_argument("--file", help="Excel (.xlsx) or CSV with column art-nr (and datum for set)")
        s.add_argument("--site", action="append", metavar="ID|NAME", help="site(s) to work on, repeatable")
        s.add_argument("--limit", type=int, metavar="N", help="only the first N articles")
        _account_flag(s)

    s = _parser(sub, "get", "read the out-of-stock delivery text per variant and site",
                "Read 'Leverans-/beställningstid, om slut i lager' (Lager, Alt. 2, free text) for\n"
                "variants, on one or more sites. The field is per site language. Read-only.\n"
                "E37's own exports do not contain this field.",
                "examples:\n  e37 delivery-text get 1526680073011 --site 'Addnature SE' --account vartex-outdoor\n"
                "  e37 delivery-text get --file lista.xlsx --site 'Addnature SE' --site 'Addnature NO' --csv nu.csv")
    common(s)
    s.add_argument("--csv", metavar="FILE", help="also write the result as a ; separated CSV")
    _json_flag(s)
    s.set_defaults(fn=cmd_delivery_get)

    s = _parser(sub, "set", "set the out-of-stock delivery text (dry run unless --apply)",
                "Set 'Leverans-/beställningstid, om slut i lager' for variants on one or more\n"
                "sites. WRITES TO E37, so:\n"
                "  - without --apply it only reads and shows what would change\n"
                "  - after each save the variant is reopened and every field compared; the\n"
                "    text must be the new one and nothing else may have changed, or the run stops\n"
                "  - one article failing is logged and the run goes on\n"
                "  - a ; separated log with old and new value is always written\n"
                "The field belongs to the site's LANGUAGE: all Swedish sites share one text. Two\n"
                "sites of one language with different texts are refused; with the same text the\n"
                "field is written once.\n"
                "Text: --text for all sites, --site-text SITE=TEXT per site; {date} is replaced\n"
                "by the date from the file's datum column.\n"
                "Run with --apply --limit 2 first on new input.",
                "examples:\n  e37 delivery-text set --file lista.xlsx --site 'Addnature SE' --text 'Förväntas åter i lager: {date}'\n"
                "  e37 delivery-text set --file lista.xlsx --site 'Addnature SE' --site 'Addnature NO' \\\n"
                "      --site-text 'Addnature SE=Förväntas åter i lager: {date}' \\\n"
                "      --site-text 'Addnature NO=Forventes tilbake på lager: {date}' --apply --limit 2")
    common(s)
    s.add_argument("--text", help="text for every site; {date} = the row's date; --text '' empties the field")
    s.add_argument("--site-text", action="append", metavar="SITE=TEXT", help="text for one site, repeatable")
    s.add_argument("--apply", action="store_true", help="really save; without it nothing is written")
    s.add_argument("--log", metavar="FILE", help="log path (default e37-leveranstid-<time>.csv here)")
    s.set_defaults(fn=cmd_delivery_set)


def _add_view_command(sub):
    kinds = "\n".join(f"  {k:<15} {t}" for k, (_, t) in registers.REGISTERS.items())
    s = _parser(sub, "view", "campaigns, discount codes, tags, pages and more in E37 Admin (read-only)",
                "List one of E37 Admin's registers, or show one item in it with every field its\n"
                "edit window has, through the person's web login. Read-only: an item is opened\n"
                "the way clicking it in E37 Admin opens it, and nothing is saved.\n\n"
                "KIND is one of:\n" + kinds + "\n\n"
                "Without REF: every item, with id, name, the list's columns and E37's status notes\n"
                "(ongoing, ended, inactive, end date). With REF (id from the list, or exact name):\n"
                "the item's fields per tab, and its ordered sub-lists, e.g. an addition set's\n"
                "articles with E37's warnings when one cannot be bought, or a tag's articles.\n"
                "Tags and pages are per site; --site picks which.",
                "examples:\n  e37 view campaigns --account vartex-outdoor --find 'black week'\n"
                "  e37 view discount-codes --account vartex-outdoor --json\n"
                "  e37 view addition-sets 3 --account vartex-outdoor --site 'Addnature SE'\n"
                "  e37 view tags sale_last_50 --account vartex-outdoor --json")
    s.add_argument("kind", choices=list(registers.REGISTERS), metavar="KIND", help="which register (see above)")
    s.add_argument("ref", nargs="?", metavar="REF", help="id or exact name of one item; omit to list")
    s.add_argument("--find", metavar="TEXT", help="only items whose name, columns or notes contain TEXT")
    s.add_argument("--site", metavar="ID|NAME", help="site to read on (default the login's current one)")
    s.add_argument("--top", type=int, default=50, metavar="N", help="sub-list rows shown without --json (default 50)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_view)

    s = _parser(sub, "change", "change fields of a campaign, discount code, tag, ... (dry run unless --apply)",
                "Change fields of one item in an E37 Admin register, the way a person does in its\n"
                "edit window. KIND and REF as for `e37 view`. Fields are named by the label `e37 view\n"
                "KIND REF` shows (or a checkbox's own label, or 'Tab/Label' when a label is on two\n"
                "tabs). Values: text as is; a list by the option's text; a checkbox ja/nej; a radio\n"
                "group by the option's label.\n\n"
                "Without --apply nothing is saved: the change is shown and logged as a dry run.\n"
                "With --apply the whole form is posted as a browser would, the item is opened again\n"
                "and EVERY field compared with before. Anything other than the named fields moving\n"
                "is reported as ANDRA FÄLT ÄNDRADES; stop then and check the item in E37 Admin.\n"
                "Each run writes a ; separated CSV log with the old and new values.\n\n"
                "Texts are per language: they are read and written for the --site's language.\n"
                "Lists inside an item (addition articles, a tag's articles, value order) and\n"
                "multi-select lists cannot be changed with this command.",
                "examples:\n  e37 change campaigns 134770 --set 'Titel i admin=FI kepsar' --account vartex-outdoor\n"
                "  e37 change campaigns 134770 --set 'Aktiverad=ja' --set 'Till=2026-11-30 23:59' --apply\n"
                "  e37 change tags 'ADD Black November' --set 'Rubrik=Black November' --site 'Addnature SE'")
    s.add_argument("kind", choices=list(registers.REGISTERS), metavar="KIND", help="which register (see `e37 view -h`)")
    s.add_argument("ref", metavar="REF", help="id or exact name of the item")
    s.add_argument("--set", action="append", metavar="FIELD=VALUE", help="a field and its new value, repeatable")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language) to work on")
    s.add_argument("--apply", action="store_true", help="really save; without it nothing is written")
    s.add_argument("--log", metavar="FILE", help="log path (default e37-andring-<time>.csv here)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_change)

    s = _parser(sub, "copy", "make a new campaign or discount code from an existing one (dry run unless --apply)",
                "Make a new campaign or discount code the way E37 Admin does: the template's Kopiera\n"
                "dialog, prefilled with all its values, with the --set fields changed, then saved.\n"
                "KIND is campaigns or discount-codes; REF the template's id or exact name.\n"
                "Fields and values as for `e37 change`. Nothing exists until --apply saves it.\n\n"
                "With --apply exactly one new item must appear, and it must hold every value the\n"
                "template's copy dialog held, with the changes. Its id is printed and logged.\n"
                "A campaign or code is often set up once per currency and site: copy one per row.",
                "examples:\n  e37 copy discount-codes 133571 --set 'Rabattkod=HOST25' --set 'Procent=25' --account vartex-outdoor\n"
                "  e37 copy campaigns 134770 --set 'Namn på kampanj=Höstrea' --set 'Aktiverad=nej' --apply")
    s.add_argument("kind", choices=["campaigns", "discount-codes"], metavar="KIND", help="campaigns or discount-codes")
    s.add_argument("ref", metavar="REF", help="id or exact name of the item to copy")
    s.add_argument("--set", action="append", metavar="FIELD=VALUE", help="a field of the new item, repeatable")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language) to work on")
    s.add_argument("--apply", action="store_true", help="really save; without it nothing is created")
    s.add_argument("--log", metavar="FILE", help="log path (default e37-kopia-<time>.csv here)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_change, copy=True)


def _add_tag_commands(sub):
    for name, remove in (("add", False), ("remove", True)):
        s = _parser(sub, name, f"{'take a tag off' if remove else 'put a tag on'} main articles (dry run unless --apply)",
                    f"{'Take an article tag off' if remove else 'Put an article tag on'} main articles, through the article "
                    "register's mass update\n(Massuppdatera artiklar → Taggar), the way a person does it for many articles "
                    "at once.\nTAG is the tag's id or exact name (see `e37 view tags`); badges are tags, often under\n"
                    "PRODUCT_HIGHLIGHT. Articles are main article numbers, as arguments or from --file.\n"
                    "Articles that already " + ("lack" if remove else "have") + " the tag are skipped.\n\n"
                    "With --apply the tag's own article list is read before and after, and must have\n"
                    "changed by exactly these articles. A CSV log lists every article.",
                    f"examples:\n  e37 tag {name} 'ADD Black November' 6200008529 1200027133 --account vartex-outdoor\n"
                    f"  e37 tag {name} 3669 --file kampanj.xlsx --apply")
        s.add_argument("tag", metavar="TAG", help="tag id or exact name")
        s.add_argument("articles", nargs="*", metavar="ART", help="main article numbers")
        s.add_argument("--file", help="Excel (.xlsx) or CSV with the column art-nr")
        s.add_argument("--site", metavar="ID|NAME", help="site to work on")
        s.add_argument("--apply", action="store_true", help="really save; without it nothing is written")
        s.add_argument("--log", metavar="FILE", help="log path (default e37-tagg-<time>.csv here)")
        _account_flag(s)
        _json_flag(s)
        s.set_defaults(fn=_cmd_tag(remove))


def _add_campaign_commands(sub):
    def articles(s):
        s.add_argument("articles", nargs="*", metavar="ART", help="main or variant article numbers")
        s.add_argument("--file", help="Excel (.xlsx) or CSV with the column art-nr")
        s.add_argument("--site", metavar="ID|NAME", help="site to work on")
        _account_flag(s)
        _json_flag(s)

    s = _parser(sub, "show", "the campaign attribute values of articles (read-only)",
                "The values of the campaign attribute Kampanj (#CAMPAIGN) on each variant of the\n"
                "given articles, from E37's own attribute export.",
                "example:\n  e37 campaign show 146355-0073 1200024087 --account vartex-outdoor")
    articles(s)
    s.set_defaults(fn=cmd_campaign_show)

    for name, remove in (("add", False), ("remove", True)):
        s = _parser(sub, name, f"{'take a campaign value off' if remove else 'put a campaign value on'} articles "
                               "(dry run unless --apply)",
                    "The campaign attribute Kampanj (#CAMPAIGN) is what campaign tags (#campaign <value>)\n"
                    "and campaign pages' product lists are made from. This "
                    + ("takes VALUE off" if remove else "adds VALUE to") + " every variant\n"
                    "of the given articles and leaves their other campaign values as they are.\n\n"
                    "Through E37's own attribute import, type 3 (only the given article and attribute\n"
                    "combinations). With --apply the attribute is exported in full before and after:\n"
                    "only these variants may have changed, and each exactly as planned. The generated\n"
                    "tags follow at E37's next sync or nightly job; --update-tags does it at once but\n"
                    "makes the import slow. A CSV log keeps the old values.",
                    f"examples:\n  e37 campaign {name} Y26HOST 146355-0073 1200024087 --account vartex-outdoor\n"
                    f"  e37 campaign {name} Y26HOST --file host.xlsx --apply")
        s.add_argument("value", metavar="VALUE", help="the campaign value, e.g. Y26MIDFASTPRIS")
        articles(s)
        s.add_argument("--update-tags", action="store_true", help="have E37 regenerate the campaign tags at once")
        s.add_argument("--apply", action="store_true", help="really import; without it nothing is written")
        s.add_argument("--log", metavar="FILE", help="log path (default e37-kampanj-<time>.csv here)")
        s.set_defaults(fn=_cmd_campaign(remove))


def _add_page_commands(sub):
    s = _parser(sub, "show", "a content page's timed versions and widgets (read-only)",
                "A content page (see `e37 view pages`): its timed versions, one per campaign, with\n"
                "their dates, and the widgets of the current version or of --version. Widgets are\n"
                "banners ('Splash') and product lists ('Artikelvy från taggsida', which shows a tag).",
                "examples:\n  e37 page show 414 --account vartex-outdoor\n  e37 page show 1328 --version 2491 --json")
    s.add_argument("page", metavar="PAGE", help="page id or exact name")
    s.add_argument("--version", metavar="ID", help="widgets of this version instead of the current one")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_page_show)

    s = _parser(sub, "widget", "one widget's settings: heading, links, tag, dates (read-only)",
                "Every setting of one widget on a content page, with the labels E37 Admin shows:\n"
                "Aktiverad, Rubrik, Från/Till, Separata länkar (button text and link), Tagg for a\n"
                "product list, layout and CSS. Texts are for the site's language.",
                "example:\n  e37 page widget 1328 132797 --account vartex-outdoor")
    s.add_argument("page", metavar="PAGE", help="page id or exact name")
    s.add_argument("widget", metavar="WIDGET", help="widget id (from `e37 page show`)")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_page_widget)

    s = _parser(sub, "change", "change a widget's settings (dry run unless --apply)",
                "Change settings of one widget, by the labels `e37 page widget` shows, as for\n"
                "`e37 change`. A product list's tag is set with --set 'Tagg=#campaign y26höst'.\n\n"
                "With --apply the widget's own Save is pressed, which E37 saves at once, then the\n"
                "widget is opened again and every one of its settings compared. A CSV log keeps\n"
                "the old values. Texts are for the --site's language.",
                "examples:\n  e37 page change 1328 132797 --set 'Rubrik=Minst 30% <br> Haglöfs' --account vartex-outdoor\n"
                "  e37 page change 1328 132800 --set 'Tagg=#campaign y26höst' --set 'Aktiverad=ja' --apply")
    s.add_argument("page", metavar="PAGE", help="page id or exact name")
    s.add_argument("widget", metavar="WIDGET", help="widget id")
    s.add_argument("--set", action="append", metavar="FIELD=VALUE", help="a setting and its new value, repeatable")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language)")
    s.add_argument("--apply", action="store_true", help="really save; without it nothing is written")
    s.add_argument("--log", metavar="FILE", help="log path (default e37-widget-<time>.csv here)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_page_change)


def _add_matrix_commands(sub):
    s = _parser(sub, "values", "an article matrix's values in display order (read-only)",
                "The values of one article matrix (Storlek, Färg, ...) in the order the shop shows them,\n"
                "for the site's language. MATRIX is its id or exact name (see `e37 view matrices`).",
                "examples:\n  e37 matrix values Storlek --find XL --account vartex-outdoor\n"
                "  e37 matrix values 33 --json")
    s.add_argument("matrix", metavar="MATRIX", help="matrix id or exact name")
    s.add_argument("--find", metavar="TEXT", help="only values containing TEXT")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_matrix_values)

    s = _parser(sub, "sort", "put some matrix values in a given order (dry run unless --apply)",
                "Put the values named in --order in that order, in the positions they already hold;\n"
                "every other value stays where it is. So 'XS,S,M,L,XL' fixes those five among\n"
                "themselves without touching the thousands of other sizes. The order is saved for\n"
                "the site's language (`--site`).\n\n"
                "With --apply the full order is read back and must be exactly the planned one.\n"
                "The CSV log holds the old order; sort back with it.",
                "examples:\n  e37 matrix sort Storlek --order 'XS,S,M,L,XL,XXL' --site 'Addnature SE'\n"
                "  e37 matrix sort Storlek --order '36,37,38,39,40' --apply")
    s.add_argument("matrix", metavar="MATRIX", help="matrix id or exact name")
    s.add_argument("--order", required=True, metavar="'A,B,C'", help="the values, comma separated, in the wanted order")
    s.add_argument("--site", metavar="ID|NAME", help="site (and thereby language)")
    s.add_argument("--apply", action="store_true", help="really save; without it nothing is written")
    s.add_argument("--log", metavar="FILE", help="log path (default e37-sortering-<time>.csv here)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_matrix_sort)


def _add_additions_commands(sub):
    s = _parser(sub, "check", "add-ons E37 warns cannot be bought, across addition sets (read-only)",
                "Open every addition set (or the --set ones) and list the add-ons E37 itself warns\n"
                "about on the site: no published variant, or no variant that can be bought there,\n"
                "with the date it last could be. A few seconds per set; there are often ~100.",
                "examples:\n  e37 additions check --site 'Addnature SE' --account vartex-outdoor\n"
                "  e37 additions check --set 3 --set 11 --site 'Addnature SE' --json")
    s.add_argument("--set", action="append", metavar="ID|NAME", help="only this addition set, repeatable")
    s.add_argument("--site", metavar="ID|NAME", help="site the warnings are for (default the login's current one)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_additions_check)

    s = _parser(sub, "swap", "replace an add-on's article in an addition set (dry run unless --apply)",
                "Replace the article of one add-on in an addition set, in place: same position, same\n"
                "settings. OLD and NEW are main article numbers (as `e37 view addition-sets ID`\n"
                "shows them). Refused when the add-on limits or preselects variants, since those\n"
                "belong to the old article.\n\n"
                "E37 saves an add-on as soon as its own dialog is saved, so --apply takes effect at\n"
                "once. Afterwards the set is opened again: the new article must be at the same\n"
                "position, the other add-ons unchanged, and every setting as before. A CSV log keeps\n"
                "the old article; swap back with OLD and NEW the other way round.",
                "examples:\n  e37 additions swap 3 1200027088 1200031280 --account vartex-outdoor\n"
                "  e37 additions swap 'Rullskidor Bindningar Skate' 1200027088 1200031280 --apply")
    s.add_argument("set", metavar="SET", help="addition set id or exact name")
    s.add_argument("old", metavar="OLD", help="article number of the add-on to replace")
    s.add_argument("new", metavar="NEW", help="article number of the replacement")
    s.add_argument("--site", metavar="ID|NAME", help="site to work on")
    s.add_argument("--apply", action="store_true", help="really save; without it nothing is written")
    s.add_argument("--log", metavar="FILE", help="log path (default e37-tillval-<time>.csv here)")
    _account_flag(s)
    _json_flag(s)
    s.set_defaults(fn=cmd_additions_swap)


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
        description="Orders, reports and products out of the E37 webshop platform. Only `change --apply`\n"
                    "and `delivery-text set --apply` write to E37.\n\n"
                    "  shop     products in a shop, no login needed\n"
                    "  order    orders: the API with a key, otherwise your own E37 Admin login\n"
                    "  report   any E37 Admin report as JSON, via your own login\n"
                    "  view     campaigns, discount codes, tags, attributes, pages, addition sets, ... (read-only)\n"
                    "  change   change fields of a campaign, discount code, tag, ... (dry run unless --apply)\n"
                    "  additions  add-ons that cannot be bought, and swapping one (dry run unless --apply)\n"
                    "  delivery-text  out-of-stock delivery text per variant (dry run unless --apply)\n"
                    "  sites    the shops your login can see\n"
                    "  account  your E37 instances, stored in the OS keychain\n"
                    "  skill    teach Claude how to use this tool\n"
                    "  update   get the latest version from GitHub",
        epilog="If you are an assistant: run `e37 skill show` for how to use this tool, and never\n"
               "ask for a password or API key in the chat; use `e37 account add NAME --dialog`.\n"
               "Every command has --help with examples.",
    )
    p.add_argument("--version", action="version", version=f"e37-cli {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{shop,order,report,view,change,copy,tag,additions,matrix,page,campaign,delivery-text,sites,account,skill,update}")

    sh = _parser(sub, "shop", "products in a shop: search, product, brands, categories, tags")
    _add_shop_commands(sh.add_subparsers(dest="shop_cmd", required=True))

    o = _parser(sub, "order", "orders from E37 Admin: flow, show, status (read-only)")
    _add_order_commands(o.add_subparsers(dest="order_cmd", required=True))

    r = _parser(sub, "report", "any E37 Admin report as JSON: list, show, get (web login)")
    _add_report_commands(r.add_subparsers(dest="report_cmd", required=True))

    _add_view_command(sub)

    tg = _parser(sub, "tag", "put a tag (badge) on articles or take it off: add, remove")
    _add_tag_commands(tg.add_subparsers(dest="tag_cmd", required=True))

    cp = _parser(sub, "campaign", "the campaign attribute on articles, which campaign tags and lists follow")
    _add_campaign_commands(cp.add_subparsers(dest="campaign_cmd", required=True))

    pg = _parser(sub, "page", "campaign pages: versions, widgets, and changing a widget")
    _add_page_commands(pg.add_subparsers(dest="page_cmd", required=True))

    mx = _parser(sub, "matrix", "article matrix values (sizes, colours): values, sort")
    _add_matrix_commands(mx.add_subparsers(dest="matrix_cmd", required=True))

    ad = _parser(sub, "additions", "addition sets: check for add-ons that cannot be bought, swap one")
    _add_additions_commands(ad.add_subparsers(dest="additions_cmd", required=True))

    dt = _parser(sub, "delivery-text", "out-of-stock delivery text per variant and site: get, set")
    _add_delivery_commands(dt.add_subparsers(dest="delivery_cmd", required=True))

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
