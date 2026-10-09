"""
The registers a marketer works in, read through the person's E37 Admin login:
campaigns, discount codes, article tags, article attributes, content pages,
content elements, widget containers, addition sets and article matrices.

None of these are in the REST API. Each register is one admin page with a list
(a table or a tree), and each item opens in a modal edit dialog through an async
postback to `__Page`, the same way the variant dialog does (see docs/web.md).

CAREFUL ABOUT WHAT IS POSTED. The postback that opens an item is the same one
that deletes or copies it; only the argument differs (`open|…` against `del|…`,
`delete|…`, `copy|…`). So the argument is never built from user input: it is
taken from the item's own link on the list page, and only for the link functions
in _OPENERS, whose JS is known to open the dialog and nothing else. Opening a
dialog does not save it. The only button pressed is Save, in change(), which
proves every save by reopening the item and comparing every field.
"""

import re
from html import unescape
from html.parser import HTMLParser

from . import E37Error
from .web import _current_site as web_current_site, _form_full

# kind: (page, Swedish title as in E37 Admin's menu)
REGISTERS = {
    "campaigns": ("workspace/workwith/prices/campaigns.aspx", "Kampanjer"),
    "discount-codes": ("workspace/workwith/prices/discountcodes.aspx", "Rabattkoder"),
    "tags": ("workspace/workwith/articles/tags.aspx", "Artikeltaggar"),
    "attributes": ("workspace/workwith/articles/attribute_list.aspx", "Artikelattribut"),
    "pages": ("workspace/layout/pages/contentpages.aspx", "Sidor"),
    "content": ("workspace/layout/contentElements.aspx", "Innehållselement"),
    "widgets": ("workspace/layout/widgets/widgets.aspx", "Widgethållare"),
    "addition-sets": ("workspace/workwith/articles/AdditionSets.aspx", "Tillvalsuppsättningar"),
    "matrices": ("workspace/workwith/articles/matrix_list.aspx", "Artikelmatriser"),
}

# The JS each list page calls to open an item, and the postback argument prefix
# that JS sends (read from E37's own scripts, 2026-10-09). Anything not here is
# never posted.
_OPENERS = {
    "openListItem": "open|",          # campaigns: openListItem('open', 134702)
    "EditDiscountCode": "open|",
    "EditArticleTag": "open_",
    "EditAttributeType": "edit_",
    "EditContentPage": "1|",
    "EditShopPage": "2|",
    "ShowCategory": "open_",
    "EditWidgetContainer": "edit_",
    "EditAdditionSets": "edit_",
    "EditMatrixType": "open_",
}
_LINK = re.compile(r"javascript:\s*(\w+)\((.*)\);?\s*$", re.S)


def items(session, kind):
    """Every item in one register on the session's current site: dicts with id, name,
    columns (the row's other cells), notes (E37's icon tooltips: status, end date,
    warnings), section (tab or heading it is listed under) and parent (tree pages)."""
    page = _page(kind)
    _, html = session._page(page)
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in _list(html)]


def item(session, kind, ref):
    """One item's edit dialog as {kind, id, name, title, fields, lists}. ref is the id
    from items() or an exact name. fields are {tab, label, value}; lists are the
    ordered sub-lists a dialog has (addition articles, a tag's articles), {tab, label, items}."""
    _, it, opened = _open(session, kind, ref)
    dialog = _dialog(opened)
    dialog.update({"kind": kind, "id": it["id"], "name": it["name"]})
    return dialog


def change(session, kind, ref, sets, apply=False, copy=False):
    """Change fields of one item the way a person does in its edit dialog. With copy,
    make a new item instead: the item's Kopiera dialog, these fields changed, saved.

    sets is [(key, value)]. key is a label as `e37 view` shows it, a checkbox's own
    label, or 'Tab/Label' when the label is on two tabs. value: text as is; a list by
    the option's text; a checkbox ja/nej; a radio group by the chosen option's label.

    Without apply only the dialog is opened, and the planned changes returned.
    With apply the whole form is posted as a browser would, with only these fields
    changed, the item is opened again and EVERY field compared with before: the
    targets must hold the new values and nothing else may have moved. Anything else
    raises E37Error, which the caller must stop on.

    A copy is proven the same way, against the Kopiera dialog: exactly one new item
    must appear in the list, and it must hold every value the dialog held, with the
    changes. Returns {"id", "name", "changes": [{"label", "old", "new"}], "saved"};
    for a copy id and name are the new item's once saved.
    """
    known = {x["id"] for x in items(session, kind)} if copy else None
    page, it, html = _open(session, kind, ref, copy=copy)
    result = {"id": it["id"], "name": it["name"]}

    def found_new():
        if copy:
            new = [x for x in items(session, kind) if x["id"] not in known]
            if len(new) != 1:
                raise E37Error(f"väntade en ny post i {REGISTERS[kind][1]} efter sparning, hittade {len(new)}. "
                               "Kontrollera i E37 Admin.")
            result.update(id=new[0]["id"], name=new[0]["name"])
        return _open(session, kind, result["id"])[2]

    result.update(_edit(session, page, html, sets, apply, reopen=found_new, always_save=copy))
    return result


_SAVE = r'name="([^"]*\$ModalPopup1\$pnl\$usrCtrl\$btnSave)"'


def _edit(session, page, html, sets, apply, reopen, scope=None, save=_SAVE, always_save=False):
    """The core of every field change: plan, post the whole form, prove it.

    html has the dialog open. scope, if given, picks the controls that belong to the
    dialog being edited (a nested one shares the page with its parent). save is the
    pattern of its Save button. reopen() returns the dialog freshly opened after the
    save. Returns {"changes", "saved"}; raises E37Error when the proof fails."""
    controls, lists = _controls(_box(html))
    if scope:
        controls = [c for c in controls if scope(c["name"])]
    site = web_current_site(html)
    plan = []
    for key, value in sets:
        group = _resolve(controls, key)
        new_form, new_shown = _convert(group, value, key)
        if _form_value(group) != new_form:
            plan.append({"label": group[0]["label"] if group[0]["kind"] != "checkbox" or not group[0]["own"]
                         else group[0]["own"], "old": _shown(group), "new": new_shown,
                         "_group": group, "_form": new_form})
    result = {"changes": [{k: v for k, v in p.items() if not k.startswith("_")} for p in plan], "saved": False}
    if not apply or not (plan or always_save):
        return result

    data = _form_full(html)
    # The page's own script sets this to 1 when the dialog loads. Left at 0 the server
    # reloads the item from the database before saving, and the change is silently lost.
    for k in data:
        if k.endswith("$usrCtrl$isPostback"):
            data[k] = "1"
    for p in plan:
        g = p["_group"]
        name = g[0]["name"]
        if g[0]["kind"] == "checkbox":
            if p["_form"]:
                data[name] = "on"
            else:
                data.pop(name, None)
        else:
            data[name] = p["_form"]
        changed_flag = f"{name.rsplit('$' + g[0]['tabkey'] + '$', 1)[0]}${g[0]['tabkey']}$changesMadeHiddenField"
        if changed_flag in data:
            data[changed_flag] = "1"
        if g[0]["lang"]:
            dirty = name[: -len(g[0]["lang"])] + "isDirty"
            if dirty in data:  # rich-text fields tell the server which languages were edited
                data[dirty] = g[0]["lang"]
    button = re.findall(save, html)
    if len(button) != 1:
        raise E37Error(f"hittade {len(button)} Spara-knappar för dialogen, avbryter")
    if web_current_site(html) != site:
        raise E37Error("fel webbplats inför skrivning, avbryter")
    data[button[0] + ".x"], data[button[0] + ".y"] = "5", "5"
    _, saved = session._page(page, data)
    result["saved"] = True
    message = _message(saved)
    said = f" E37 sa: {message}" if message else ""

    again = reopen()
    if web_current_site(again) != site:
        raise E37Error("webbplatsen byttes under sparningen; kontrollera posten i E37 Admin")
    after, after_lists = _controls(_box(again))
    if scope:
        after = [c for c in after if scope(c["name"])]
    before = {c["name"] + ("=" + c["value"] if c["kind"] == "radio" else ""): c for c in controls}
    now = {c["name"] + ("=" + c["value"] if c["kind"] == "radio" else ""): c for c in after}
    targets = {c["name"] for p in plan for c in p["_group"]}
    moved = sorted(c["label"] for k, c in before.items()
                   if c["name"] not in targets and (k not in now or _form_value([now[k]]) != _form_value([c])))
    moved += sorted(c["label"] for k, c in now.items() if k not in before and c["name"] not in targets)
    if moved or (not scope and after_lists != lists):
        raise E37Error("ANDRA FÄLT ÄNDRADES vid sparning: " + ", ".join((moved or ["underlistor"])[:8])
                       + ". Stanna och kontrollera posten i E37 Admin." + said)
    for p in plan:
        group = [c for c in after if c["name"] == p["_group"][0]["name"]]
        if not group or _form_value(group) != p["_form"]:
            raise E37Error(f"{p['label']}: sparat värde är {_shown(group)!r}, inte {p['new']!r}." + said)
    return result


_P = "ctl00$cph1$ModalPopup1$pnl$usrCtrl"
_SUB = _P + "$imp$pnl$usrCtrl"
ARTICLE_SEARCH = "service/autoCompleteArticlesExcludePackages"


def find_article(session, art_nr):
    """(main id, name, art nr) for an exact main article number, through the same
    search the admin's article fields use. Exactly one, or an error."""
    from urllib.parse import quote
    import json
    _, body = session._page(f"{ARTICLE_SEARCH}?query={quote(art_nr)}")
    hits = [s["data"].split("|") for s in json.loads(body).get("suggestions", [])]
    hits = [h for h in hits if len(h) >= 3 and h[-1] == art_nr]
    if len(hits) != 1:
        raise E37Error(f"hittade {len(hits)} artiklar med exakt artikelnummer {art_nr}")
    return hits[0][0], "|".join(hits[0][1:-1]), hits[0][-1]


def _additions(html):
    """[(position, art nr, text, notes, edit argument)] of an open addition set, in order."""
    out = []
    for i, n in enumerate(_box(html).find_all(lambda x: "dragAndDropItem" in x.cls.split()), 1):
        main = n.find(lambda x: "innerMainArea" in x.cls.split())
        text = main.text() if main else ""
        parts = [p.strip() for p in text.split(",")]
        link = n.find(lambda x: x.tag == "a" and "EditAdditionalArticle" in x.attrs.get("href", ""))
        arg = re.search(r'EditAdditionalArticle\("([^"]*)"\)', unescape(link.attrs["href"])).group(1) if link else None
        notes = [_title(x) for x in n.find_all(lambda x: x.tag == "img" and x.attrs.get("title"))]
        out.append((i, parts[1] if len(parts) > 1 else "", text, notes, arg))
    return out


def unbuyable(session, sets=None, progress=None):
    """Add-ons E37 warns about on the session's site: [{set_id, set, position, art_nr,
    text, notes}]. Opens every addition set (or those in sets), a few seconds each."""
    rows = items(session, "addition-sets")
    if sets:
        rows = [r for r in rows if r["id"] in sets or r["name"] in sets]
    out = []
    for k, r in enumerate(rows, 1):
        if progress:
            progress(k, len(rows), r["name"])
        _, it, html = _open(session, "addition-sets", r["id"])
        for pos, art, text, notes, _ in _additions(html):
            if notes:
                out.append({"set_id": it["id"], "set": it["name"], "position": pos, "art_nr": art,
                            "text": text, "notes": notes})
    return out


def swap_addition(session, set_ref, old_art, new_art, apply=False):
    """Replace the article of one add-on in an addition set, in place: same position,
    same settings. E37 saves an add-on as soon as its own dialog is saved.

    Refused when the add-on limits or preselects variants, since those belong to the
    old article. With apply the set and the add-on are opened again afterwards: the
    new article must sit at the same position, every other add-on be unchanged, and
    every setting of the add-on be as before."""
    page, it, html = _open(session, "addition-sets", set_ref)
    before = _additions(html)
    hit = [a for a in before if a[1] == old_art]
    if len(hit) != 1:
        raise E37Error(f"{it['name']}: {len(hit)} tillval med artikelnummer {old_art}. "
                       f"Tillvalen är: {', '.join(a[1] for a in before)}")
    pos, _, old_text, _, arg = hit[0]
    if any(a[1] == new_art for a in before):
        raise E37Error(f"{it['name']}: {new_art} är redan ett tillval i uppsättningen")
    new_id, new_name, _ = find_article(session, new_art)
    result = {"set_id": it["id"], "set": it["name"], "position": pos, "old": old_text,
              "new": f"{new_art}, {new_name}", "saved": False}

    sub_html = _post(session, page, html, {"__EVENTTARGET": _P, "__EVENTARGUMENT": arg})
    settings = _sub_settings(sub_html)
    for label in ("Förvald artikelvariant", "Begränsa val"):
        v = settings.get(label, "")
        if v and v not in ("(Ingen förvald artikelvariant)", "Begränsa valbara artikelvarianter: nej"):
            raise E37Error(f"{it['name']}: tillvalet {old_art} har '{label}: {v}', som hör till den gamla "
                           f"artikeln. Byt det i E37 Admin i stället.")
    if not apply:
        return result

    picked = _post(session, page, sub_html, {"__EVENTTARGET": _SUB + "$PopupTab1$autoArticle",
                                             "__EVENTARGUMENT": f"{new_id}|{new_name}|{new_art}",
                                             _SUB + "$PopupTab1$changesMadeHiddenField": "1"})
    saved = _post(session, page, picked, {_SUB + "$btnSave.x": "5", _SUB + "$btnSave.y": "5"})
    result["saved"] = True
    message = _message(saved)

    _, _, again = _open(session, "addition-sets", it["id"])
    after = _additions(again)
    expected = [(a[0], new_art if a[0] == pos else a[1]) for a in before]
    if [(a[0], a[1]) for a in after] != expected:
        raise E37Error(f"{it['name']}: tillvalen blev {', '.join(a[1] for a in after)}, väntade "
                       f"{', '.join(a for _, a in expected)}. Kontrollera i E37 Admin."
                       + (f" E37 sa: {message}" if message else ""))
    new_arg = after[pos - 1][4]
    now = _sub_settings(_post(session, page, again, {"__EVENTTARGET": _P, "__EVENTARGUMENT": new_arg}))
    skip = {"AutoCompleteTB", "Valbara artikelvarianter"}
    moved = sorted(k for k in set(settings) | set(now) if k not in skip and settings.get(k) != now.get(k))
    if moved:
        raise E37Error(f"{it['name']}: ANDRA INSTÄLLNINGAR ÄNDRADES på tillvalet: {', '.join(moved)}. "
                       f"Kontrollera i E37 Admin.")
    return result


TAG_SEARCH = "service/autoSuggestTagsExcludeGeneratedByAttribute"
_MASS = "ctl00$cph1$mod1$pnl$usrCtrl"
_ARTICLES = "workspace/workwith/articles/list.aspx"


def tag_articles(session, tag_ref, art_nrs, remove=False, apply=False, chunk=200):
    """Put a tag on main articles, or take it off, through the article register's
    mass update ("Massuppdatera artiklar" → Taggar → Lägg till/Ta bort tagg).

    art_nrs are main article numbers. Those that already have (or lack) the tag are
    skipped. With apply the tag's own article list is read before and after: it must
    have changed by exactly these articles. Returns {tag, change, unchanged, saved}."""
    from urllib.parse import quote
    import json
    tag = _one_item(session, "tags", tag_ref)
    _, body = session._page(f"{TAG_SEARCH}?term={quote(tag['name'])}")
    sugg = [t for t in json.loads(body) if t.get("value") == tag["id"]]
    if len(sugg) != 1:
        raise E37Error(f"taggen {tag['name']} ({tag['id']}) går inte att välja i massuppdateringen "
                       f"(genererad från ett attribut?)")
    before = _tagged(session, tag["id"])
    arts = [find_article(session, a) for a in dict.fromkeys(art_nrs)]
    change = [a for a in arts if (a[2] in before) == remove]
    result = {"tag": f"{tag['name']} ({tag['id']})", "change": [f"{a[2]} {a[1]}" for a in change],
              "unchanged": [a[2] for a in arts if a not in change], "saved": False}
    if not apply or not change:
        return result
    mode = "Ta bort tagg" if remove else "Lägg till tagg"
    s = sugg[0]
    hidden2 = json.dumps([{"value": s["value"], "label": s["label"], "concat": s["concat"], "Treeview": None,
                           "icon": None, "iconTooltip": None, "extraCssClass": ""}], ensure_ascii=False)
    for i in range(0, len(change), chunk):
        part = change[i:i + chunk]
        _, page = session._page(_ARTICLES)
        data = _form_full(page)
        data.update({"__EVENTTARGET": "__Page", "__EVENTARGUMENT": "massupdate_" + json.dumps([int(a[0]) for a in part])})
        _, html = session._page(_ARTICLES, data)
        box = _box(html)
        if box is None or "Massuppdatera" not in html:
            raise E37Error("massuppdateringen gick inte att öppna")
        radio = [c for c in _controls(box)[0] if c["kind"] == "radio" and c["own"] == mode]
        if len(radio) != 1:
            raise E37Error(f"hittade inte valet '{mode}' i massuppdateringen")
        _post(session, _ARTICLES, html, {
            _MASS + "$PopupTab1$cbUpdateTags": "on", radio[0]["name"]: radio[0]["value"],
            _MASS + "$PopupTab1$articleTags$AutoSuggestHidden": s["concat"] + ";",
            _MASS + "$PopupTab1$articleTags$AutoSuggestHidden2": hidden2,
            _MASS + "$PopupTab1$changesMadeHiddenField": "1",
            _MASS + "$btnSave.x": "5", _MASS + "$btnSave.y": "5"})
        result["saved"] = True
    after = _tagged(session, tag["id"])
    names = {a[2] for a in change}
    expected = (before - names) if remove else (before | names)
    if after != expected:
        missing, extra = sorted(expected - after), sorted(after - expected)
        raise E37Error(f"taggen {tag['name']}: efter sparning "
                       + (f"saknas {', '.join(missing[:10])} " if missing else "")
                       + (f"finns oväntat {', '.join(extra[:10])} " if extra else "")
                       + "— kontrollera i E37 Admin.")
    return result


def _one_item(session, kind, ref):
    return _match(items(session, kind), kind, ref)


def _match(found, kind, ref):
    """The one item ref names: an id, or an exact name. A ref that is one item's id and
    another's name (a page called "414" next to the page with id 414) is refused."""
    ref = str(ref).strip()
    by_id = [it for it in found if ref == it["id"]]
    by_name = [it for it in found if ref.lower() == it["name"].lower()]

    def show(hs):
        return ", ".join(f"{h['parent'] + ' › ' if h.get('parent') else ''}{h['name']} ({h['id']})" for h in hs[:10])
    if by_id and by_name and {h["id"] for h in by_name} != {by_id[0]["id"]}:
        raise E37Error(f"{ref!r} är både id för {show(by_id)} och namn på {show(by_name)} i "
                       f"{REGISTERS[kind][1]}. Ange id för den som avses.")
    hits = by_id or by_name
    if len({it["id"] for it in hits}) != 1:
        near = hits or [it for it in found if ref.lower() in it["name"].lower()]
        raise E37Error(f"{'Flera' if hits else 'Ingen'} post i {REGISTERS[kind][1]} heter exakt {ref!r}"
                       + (f". {'Välj med id' if hits else 'Menade du'}: {show(near)}" if near else f". Lista med: e37 view {kind}"))
    return hits[0]


def _tagged(session, tag_id):
    """Main article numbers on a tag, from the tag's own Artiklar tab."""
    d = item(session, "tags", tag_id)
    return {i["text"].split(" ", 1)[0] for lst in d["lists"] if lst["tab"] == "Artiklar" for i in lst["items"]}


_SORT_LT = _SUB + "$PopupTab1$LanguageTabContainer1"


def matrix_values(session, ref):
    """[(value id, value)] of an article matrix, in the order the site's language shows them."""
    _, _, html = _matrix_sort_dialog(session, ref)
    return _sort_order(html)


def sort_matrix(session, ref, wanted, apply=False):
    """Put some of a matrix's values in the given order, in the positions they already
    hold: the rest stay where they are. Saved for the site's language. With apply the
    order is read back and must be exactly the planned one.
    Returns {matrix, before, after, saved}, the orders as value names."""
    page, it, html = _matrix_sort_dialog(session, ref)
    current = _sort_order(html)
    names = [v for _, v in current]
    missing = [w for w in wanted if w not in names]
    if missing:
        raise E37Error(f"{it['name']}: värdena finns inte: {', '.join(missing[:10])}")
    if len(set(wanted)) != len(wanted) or any(names.count(w) > 1 for w in wanted):
        raise E37Error(f"{it['name']}: ett värde förekommer två gånger; ange varje värde en gång")
    slots = [i for i, v in enumerate(names) if v in wanted]
    planned = list(current)
    for slot, w in zip(slots, wanted):
        planned[slot] = next(c for c in current if c[1] == w)
    result = {"matrix": f"{it['name']} ({it['id']})", "before": [v for _, v in current],
              "after": [v for _, v in planned], "saved": False}
    if not apply or planned == current:
        return result
    key = _SORT_LT.replace("$", "_") + "_dragAndDropItem[]"
    html = _post(session, page, html, {"__EVENTTARGET": _SORT_LT + "$dragAndDrop",
                                       "__EVENTARGUMENT": "&".join(f"{key}={i}" for i, _ in planned)})
    _post(session, page, html, {_SUB + "$PopupTab1$changesMadeHiddenField": "1",
                                _SUB + "$btnSave.x": "5", _SUB + "$btnSave.y": "5"})
    result["saved"] = True
    now = matrix_values(session, it["id"])
    if now != planned:
        raise E37Error(f"{it['name']}: ordningen blev inte den planerade. Kontrollera i E37 Admin.")
    return result


def _matrix_sort_dialog(session, ref):
    page, it, html = _open(session, "matrices", ref)
    button = re.findall(r'name="([^"]*\$btnSortMatrixValues)"', html)
    if not button:
        raise E37Error(f"{it['name']}: hittade ingen sorteringsknapp")
    return page, it, _post(session, page, html, {button[0] + ".x": "5", button[0] + ".y": "5"})


def _sort_order(html):
    return [(m.group(1), unescape(m.group(2)))
            for m in re.finditer(r'\$matrixValue_(\d+)" type="text" value="([^"]*)"', html)]


def _post(session, page, html, extra):
    data = _form_full(html)
    for k in data:
        if k.endswith("$usrCtrl$isPostback"):
            data[k] = "1"
    data.update(extra)
    return session._page(page, data)[1]


def _sub_settings(html):
    """The add-on dialog's settings, label -> shown value (several values joined)."""
    out = {}
    for c in _controls(_box(html))[0]:
        if "$imp$" in c["name"] and c["shown"]:
            out[c["label"]] = "; ".join(v for v in (out.get(c["label"]), c["shown"]) if v)
    return out


def _open(session, kind, ref, copy=False):
    """(page, list item, html with the item's dialog open, or its Kopiera dialog)."""
    page = _page(kind)
    _, html = session._page(page)
    it = _match(_list(html), kind, ref)
    if copy and not it["_copy"]:
        raise E37Error(f"{REGISTERS[kind][1]}: posten {it['id']} går inte att kopiera härifrån")
    data = _form_full(html)
    data.update({"__EVENTTARGET": "__Page", "__EVENTARGUMENT": it["_copy"] if copy else it["_arg"]})
    _, opened = session._page(page, data)
    if _box(opened) is None:
        raise E37Error(f"{REGISTERS[kind][1]}: posten {it['id']} gick inte att öppna")
    return page, it, opened


def _resolve(controls, key):
    """The control (or radio group) a key names; exactly one, or an error with the candidates."""
    locked = [c for c in controls if c["disabled"] and key.strip().lower() in (c["label"].lower(), (c["own"] or "").lower())]
    if locked:
        raise E37Error(f"{key!r} är låst i E37 Admin för den här posten och går inte att ändra")
    usable = [c for c in controls if not c["disabled"]]
    tab, label = None, key.strip()
    for t in {c["tab"] for c in usable}:
        if t and label.lower().startswith(t.lower() + "/"):
            tab, label = t, label[len(t) + 1:].strip()
    if tab:
        usable = [c for c in usable if c["tab"] == tab]
    k = label.lower()
    hits = ([c for c in usable if c["kind"] == "checkbox" and (c["own"] or "").lower() == k]
            or [c for c in usable if c["label"].lower() == k]
            or [c for c in usable if c["name"].split("$")[-1].lower() == k])
    names = {c["name"] for c in hits}
    if len(names) != 1:
        known = sorted({f"{c['tab']}/{c['own'] if c['kind'] == 'checkbox' and c['own'] else c['label']}"
                        for c in (hits or usable)})
        raise E37Error(f"{'Flera fält' if hits else 'Inget fält'} heter {key!r}. "
                       + ("Ange flik: " if hits else "Fält: ") + "; ".join(known[:40]))
    return [c for c in hits if c["name"] in names]


def _form_value(group):
    c = group[0]
    if c["kind"] == "radio":
        return next((r["value"] for r in group if r.get("checked")), None)
    if c["kind"] == "select":
        return c["value"][0] if c["value"] else ""
    if c["kind"] == "multiselect":
        return list(c["value"])
    return c["value"]


def _shown(group):
    if not group:
        return None
    c = group[0]
    if c["kind"] == "radio":
        return next((r["own"] or r["value"] for r in group if r.get("checked")), "")
    if c["kind"] == "checkbox":
        return "ja" if c["value"] else "nej"
    return c["shown"]


_YES, _NO = {"ja", "j", "yes", "y", "true", "on", "1"}, {"nej", "n", "no", "false", "off", "0", ""}


def _convert(group, value, key):
    """(what the form posts, what the UI shows) for a value given by a person."""
    c = group[0]
    v = str(value)
    if c["kind"] == "checkbox":
        if v.strip().lower() in _YES:
            return True, "ja"
        if v.strip().lower() in _NO:
            return False, "nej"
        raise E37Error(f"{key}: en kryssruta tar ja eller nej, inte {v!r}")
    if c["kind"] in ("select", "radio"):
        opts = c["options"] if c["kind"] == "select" else [(r["value"], r["own"] or r["value"]) for r in group]
        def norm(x):   # tree lists indent their options with "- ", "-- "
            return re.sub(r"^[\s\-–]+", "", x).strip().lower()
        hit = ([o for o in opts if o[1].strip().lower() == v.strip().lower()]
               or [o for o in opts if norm(o[1]) == norm(v)] or [o for o in opts if o[0] == v])
        if len({o[0] for o in hit}) != 1:
            near = [o[1] for o in opts if v.strip().lower() in o[1].lower()][:15]
            raise E37Error(f"{key}: {'flera val' if hit else 'inget val'} heter {v!r}."
                           + (f" Närmast: {'; '.join(near)}" if near else f" Val: {'; '.join(o[1] for o in opts[:30])}"))
        return hit[0][0], hit[0][1]
    if c["kind"] == "multiselect":
        raise E37Error(f"{key}: flervalslistor går inte att ändra än")
    return v, v


def _message(html):
    """Text E37 shows in its message box after a postback, if any."""
    root = _dom(html)
    texts = [n.text() for n in root.find_all(lambda n: "msgBoxCell2" in n.attrs.get("id", "")
                                             or "msgBox_lbl" in n.attrs.get("id", ""))]
    return " ".join(t for t in texts if t and t != "OK") or None


def _page(kind):
    if kind not in REGISTERS:
        raise E37Error(f"Okänd sort {kind!r}. Välj bland: {', '.join(REGISTERS)}")
    return REGISTERS[kind][0]


def _open_arg(href):
    """The postback argument an opener link sends, or None for any other link."""
    m = _LINK.match(unescape(href or "").strip())
    if not m or m.group(1) not in _OPENERS:
        return None, None
    fn, args = m.group(1), [a.strip().strip("'\"") for a in m.group(2).split(",")]
    if fn == "openListItem":
        if len(args) != 2 or args[0] != "open" or not args[1].isdigit():
            return None, None
        return _OPENERS[fn] + args[1], args[1]
    q = args[0]
    ident = re.search(r"\bid=(\d+);", q)
    if len(args) != 1 or not ident:
        return None, None
    return _OPENERS[fn] + q, ident.group(1)


# The JS a list row's Kopiera button calls, and what it posts (read from E37's own
# scripts, 2026-10-09). It opens a prefilled "Kopiera …" dialog; nothing is created
# until that dialog is saved (verified on a discount code).
_COPIERS = {"CopyDiscountCode": "copy|", "openListItem": "copy|"}


def _copy_arg(js):
    m = re.search(r"(\w+)\(([^)]*)\)", unescape(js or ""))
    if not m or m.group(1) not in _COPIERS:
        return None
    args = [a.strip().strip("'\"") for a in m.group(2).split(",")]
    if m.group(1) == "openListItem":
        return _COPIERS["openListItem"] + args[1] if len(args) == 2 and args[0] == "copy" and re.fullmatch(r"\d+;", args[1]) else None
    return _COPIERS[m.group(1)] + args[0] if len(args) == 1 and re.match(r"id=\d+;", args[0]) else None


# ---- list pages ----------------------------------------------------------------

def _list(html):
    root = _dom(html)
    work = root.find(lambda n: "workplace" in n.cls) or root
    tabs = [t.text() for t in work.find_all(lambda n: n.tag == "a" and n.attrs.get("data-tabid") is not None)]
    out, seen = [], set()
    heading = None
    for n in work.walk():
        if n.tag == "h3":
            heading = n.text()
        if n.tag != "a":
            continue
        arg, ident = _open_arg(n.attrs.get("href"))
        if not arg or ident in seen:
            continue
        seen.add(ident)
        row = n.closest(lambda p: p.tag == "tr" or "item" in p.cls.split())
        cells = row.children_el() if row else []
        name = n.text()
        columns = [c.text() for c in cells if c.text() and name not in c.text()]
        notes = [_title(i) for i in (row or n).find_all(lambda x: x.tag == "img" and x.attrs.get("title"))]
        tab = n.closest(lambda p: re.search(r"\btabContent-\d+\b", p.cls))
        k = re.search(r"\btabContent-(\d+)\b", tab.cls) if tab else None
        section = tabs[int(k.group(1))] if k and int(k.group(1)) < len(tabs) else heading
        node = n.closest(lambda p: "node" in p.cls.split())
        parent = node.parent.closest(lambda p: "node" in p.cls.split()) if node and node.parent else None
        pname = None
        if parent:
            pa = parent.find(lambda x: x.tag == "a" and _open_arg(x.attrs.get("href"))[0])
            pname = pa.text() if pa else None
        copy = next((c for c in (_copy_arg(x.attrs.get("onclick") or x.attrs.get("href"))
                                 for x in (row or n).walk()) if c), None)
        out.append({"id": ident, "name": name, "columns": columns, "notes": notes,
                    "section": section, "parent": pname, "_arg": arg, "_copy": copy})
    return out


# ---- edit dialog ---------------------------------------------------------------

def _box(html):
    root = _dom(html)
    return root.find(lambda n: "modalpopup" in n.cls.split() and n.find(lambda x: "popupTabContent" in x.cls.split()))


def _dialog(html):
    """The open dialog as {title, fields, lists} for reading, or None if none is open."""
    box = _box(html)
    if box is None:
        return None
    controls, lists = _controls(box)
    head = box.find(lambda n: "topContent" in n.cls.split())
    fields = [{"tab": c["tab"], "label": c["label"], "value": c["shown"]}
              for c in controls if c["shown"] not in (None, "")]
    return {"title": head.text() if head else "", "fields": _merge(fields), "lists": lists}


def _controls(box):
    """Every field in a dialog, with what writing needs: the form name, its tab,
    the label the UI shows (and a checkbox's or radio's own label), its kind,
    its options, and what it shows now. Plus the dialog's ordered sub-lists."""
    tabnames = {}
    for li in box.find_all(lambda n: n.tag == "li" and "popupTabItem|" in n.attrs.get("id", "")):
        tabnames[li.attrs["id"].split("|")[-1]] = li.text()
    labels = {x.attrs["for"]: x.text() for x in box.find_all(lambda x: x.tag == "label" and x.attrs.get("for"))}
    controls, lists = [], []
    for tab in box.find_all(lambda n: "popupTabContent" in n.cls.split()):
        tabkey = tab.attrs.get("id", "").split("_")[-1]
        tname = tabnames.get(tabkey, "")
        label = None
        rows = {id(r) for r in tab.find_all(_item_row)}
        for n in tab.walk():
            if "triton-label" in n.cls.split() or (n.tag == "label" and not n.attrs.get("for")
                                                   and not n.closest(lambda p: "triton-label" in p.cls.split())):
                label = n.text().rstrip(":").strip()
            elif id(n) in rows:
                # A row in a dialog's item table (a tag's articles), with only a remove box.
                if not lists or lists[-1]["tab"] != tname or lists[-1].get("label") != label:
                    lists.append({"tab": tname, "label": label, "items": []})
                lists[-1]["items"].append({"text": n.text()})
            elif "dragAndDropItem" in n.cls.split():
                main = n.find(lambda x: "innerMainArea" in x.cls.split())
                notes = [_title(i) for i in n.find_all(lambda x: x.tag == "img" and x.attrs.get("title"))]
                entry = {"text": main.text() if main else n.text()}
                if notes:
                    entry["notes"] = notes
                if not lists or lists[-1]["tab"] != tname or lists[-1].get("label") != label:
                    lists.append({"tab": tname, "label": label, "items": []})
                lists[-1]["items"].append(entry)
            elif n.tag in ("input", "select", "textarea") and n.attrs.get("name"):
                if n.closest(lambda p: id(p) in rows or "dragAndDropItem" in p.cls.split()):
                    continue
                c = _control(n, labels)
                if c is None or c["name"].endswith("$cbCheckAll"):
                    continue
                if c["own"] and c["kind"] not in ("checkbox", "radio"):
                    lab, c["own"] = c["own"], None   # a <label for=…> names a text field or list itself
                else:
                    lab = _row_label(n) or label or c["own"] or c["name"].split("$")[-1]
                if c["own"] == lab:
                    c["own"] = None
                if c["lang"] and c["lang"] not in lab:
                    lab = f"{lab} [{c['lang']}]"
                c.update(tab=tname, tabkey=tabkey, label=lab)
                if c["shown"] and c["own"] and c["kind"] == "checkbox":
                    c["shown"] = f"{c['own']}: {c['shown']}"
                controls.append(c)
    return controls, lists


def _control(n, labels):
    """One form control, or None for the ones a person never sets (hidden, buttons)."""
    t = (n.attrs.get("type") or "text").lower()
    name = n.attrs["name"]
    last = name.split("$")[-1]
    # Widget settings label by the field's short name (for="str_423"), not its id.
    c = {"name": name, "own": labels.get(n.attrs.get("id")) or labels.get(last), "options": [],
         "lang": last if re.fullmatch(r"[a-z]{2}", last) else None,
         "disabled": "disabled" in n.attrs}
    if n.tag == "select":
        opts = n.find_all(lambda o: o.tag == "option")
        c["options"] = [(o.attrs.get("value", o.text()), o.text()) for o in opts]
        sel = [o for o in opts if "selected" in o.attrs]
        if not sel and opts and "multiple" not in n.attrs:
            sel = opts[:1]
        c.update(kind="multiselect" if "multiple" in n.attrs else "select",
                 value=[o.attrs.get("value", o.text()) for o in sel],
                 shown=", ".join(o.text() for o in sel))
        return c
    if n.tag == "textarea":
        v = n.text(raw=True)
        v = v[1:] if v.startswith("\n") else v
        c.update(kind="textarea", value=v, shown=v.strip())
        return c
    if t in ("hidden", "submit", "image", "button", "file", "password", "reset"):
        return None
    if t == "checkbox":
        on = "checked" in n.attrs
        c.update(kind="checkbox", value=on, shown="ja" if on else "nej")
        return c
    if t == "radio":
        on = "checked" in n.attrs
        c.update(kind="radio", value=n.attrs.get("value", ""), checked=on,
                 shown=(c["own"] or n.attrs.get("value", "")) if on else None)
        return c
    v = unescape(n.attrs.get("value", ""))
    c.update(kind="text", value=v, shown=v)
    return c


def _title(n):
    return re.sub(r"\s*\r?\n\s*", "\n", n.attrs["title"]).strip()


def _row_label(n):
    """In a form laid out as a table, the nearest cell before the field's own that has text
    (a <label>, or a description column as in content elements)."""
    td = n.closest(lambda p: p.tag == "td")
    if td is None or td.parent is None:
        return None
    cells = td.parent.children_el()
    for c in reversed(cells[:cells.index(td)]):
        if c.tag in ("td", "th") and c.text():
            return c.text().rstrip(":").strip()
    return None


def _item_row(n):
    return n.tag == "tr" and n.find(lambda x: re.search(r"\$cbDelete_\d+$", x.attrs.get("name", ""))) is not None


def _merge(fields):
    """One entry per label: checkboxes and multi-part fields under one label are joined."""
    out = []
    for f in fields:
        if out and out[-1]["tab"] == f["tab"] and out[-1]["label"] == f["label"] and f["value"] != "":
            out[-1]["value"] = "; ".join(v for v in (out[-1]["value"], f["value"]) if v)
        elif not (out and out[-1]["tab"] == f["tab"] and out[-1]["label"] == f["label"]):
            out.append(dict(f))
    return out


# ---- content pages: versions and widgets --------------------------------------
#
# A campaign page is a content page with timed versions, one per campaign, each with
# its own widgets (banners, product lists from a tag). The page dialog lists them;
# a widget opens in a dialog nested in the page dialog. Opening a widget while a
# version dialog is open makes E37 fail ("An item with the same key has already been
# added"), so each widget is opened from a freshly opened page. See docs/web.md.

_INSERT_WIDGET = re.compile(r"InsertWidget\('(\d+)', '((?:[^'\\]|\\.)*)', '[^']*', '[^']*', '([^']*)'")
_IN_WIDGET = re.compile(r"\$imp\$pnl\$usrCtrl\$")
_WIDGET_SAVE = r'name="([^"]*\$ModalPopup1\$pnl\$usrCtrl\$imp\$pnl\$usrCtrl\$btnSave)"'


def page(session, ref, version=None):
    """A content page's versions [{id, title, from, to}] and the widgets [{id, title,
    type}] of its current version, or of the given version id."""
    import json
    pg, it, html = _open(session, "pages", ref)
    versions = []
    for a in _box(html).find_all(lambda n: n.tag == "a" and "EditVersion(" in n.attrs.get("href", "")):
        vid = re.search(r"id=(\d+);", unescape(a.attrs["href"])).group(1)
        row = a.closest(lambda p: p.tag == "tr")
        cells = [c.text() for c in row.children_el()] if row else [a.text()]
        dates = [c for c in cells if re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", c)]
        versions.append({"id": vid, "title": a.text() or next((c for c in cells if c), ""),
                         "from": dates[0] if dates else None, "to": dates[1] if len(dates) > 1 else None})
    source = html
    if version:
        if str(version) not in {v["id"] for v in versions}:
            raise E37Error(f"sidan {it['name']} har ingen version {version}")
        source = _post(session, pg, html, {"__EVENTTARGET": _P, "__EVENTARGUMENT": f"editV_id={int(version)};"})
    widgets = [{"id": i, "title": json.loads('"' + t.replace('"', '\\"') + '"'), "type": ty}
               for i, t, ty in _INSERT_WIDGET.findall(source)]
    return {"id": it["id"], "name": it["name"], "versions": versions, "widgets": widgets}


def widget(session, page_ref, widget_id):
    """One widget's settings as {page, id, title, fields}, like item() for a register."""
    _, it, html = _open_widget(session, page_ref, widget_id)
    controls, _ = _controls(_box(html))
    fields = [{"tab": c["tab"], "label": c["label"], "value": c["shown"]}
              for c in controls if _IN_WIDGET.search(c["name"]) and c["shown"] not in (None, "")]
    return {"page": f"{it['name']} ({it['id']})", "id": str(widget_id), "fields": _merge(fields)}


def change_widget(session, page_ref, widget_id, sets, apply=False):
    """Change fields of one widget on a content page, like change() for a register item:
    dry run unless apply; with apply the widget's own Save, then the widget opened again
    and every one of its fields compared. Returns {page, id, changes, saved}."""
    pg, it, html = _open_widget(session, page_ref, widget_id)
    result = {"page": f"{it['name']} ({it['id']})", "id": str(widget_id)}
    result.update(_edit(session, pg, html, sets, apply,
                        reopen=lambda: _open_widget(session, it["id"], widget_id)[2],
                        scope=lambda name: bool(_IN_WIDGET.search(name)), save=_WIDGET_SAVE))
    return result


def _open_widget(session, page_ref, widget_id):
    pg, it, html = _open(session, "pages", page_ref)
    site = web_current_site(html)
    # A widget of another version is not drawn on the page dialog; it still opens by id.
    opened = _post(session, pg, html, {"__EVENTTARGET": _P,
                                       "__EVENTARGUMENT": f"edit_id={int(widget_id)};siteid={site};"})
    err = re.search(r"Teknisk information</h3>\s*([^<]{0,160})", opened)
    if err or _box(opened) is None or not _IN_WIDGET.search(opened):
        raise E37Error(f"widget {widget_id} på sidan {it['name']} gick inte att öppna"
                       + (f": {err.group(1).strip()}" if err else ""))
    return pg, it, opened

# ---- a small DOM on html.parser ------------------------------------------------

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    @property
    def cls(self):
        return self.attrs.get("class") or ""

    def walk(self):
        for c in self.children:
            if isinstance(c, _Node):
                yield c
                yield from c.walk()

    def find(self, pred):
        return next((n for n in self.walk() if pred(n)), None)

    def find_all(self, pred):
        return [n for n in self.walk() if pred(n)]

    def closest(self, pred):
        n = self
        while n is not None and n.tag is not None:
            if pred(n):
                return n
            n = n.parent
        return None

    def children_el(self):
        return [c for c in self.children if isinstance(c, _Node)]

    def text(self, raw=False):
        parts = []

        def rec(n):
            for c in n.children:
                if isinstance(c, str):
                    parts.append(c)
                elif c.tag not in ("script", "style", "option") or c is self:
                    rec(c)
                    if c.tag in ("br", "div", "p", "li", "td"):
                        parts.append(" ")
        rec(self)
        s = "".join(parts)
        return s if raw else re.sub(r"\s+", " ", s).strip()


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node(None, {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = _Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(n)
        if tag not in _VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def _dom(html):
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root
