"""
The registers a marketer works in, read through the person's E37 Admin login:
campaigns, discount codes, article tags, article attributes, content pages,
content elements, widget containers, addition sets and article matrices.

None of these are in the REST API. Each register is one admin page with a list
(a table or a tree), and each item opens in a modal edit dialog through an async
postback to `__Page`, the same way the variant dialog does (see docs/web.md).

READ ONLY, AND CAREFUL ABOUT IT. The postback that opens an item is the same one
that deletes or copies it; only the argument differs (`open|…` against `del|…`,
`delete|…`, `copy|…`). So the argument is never built from user input: it is
taken from the item's own link on the list page, and only for the link functions
in _OPENERS, whose JS is known to open the dialog and nothing else. Nothing here
presses a button in a dialog, and opening one does not save it.
"""

import re
from html import unescape
from html.parser import HTMLParser

from . import E37Error
from .web import _form_full

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
    return [{k: v for k, v in it.items() if k != "_arg"} for it in _list(html)]


def item(session, kind, ref):
    """One item's edit dialog as {kind, id, name, title, fields, lists}. ref is the id
    from items() or an exact name. fields are {tab, label, value}; lists are the
    ordered sub-lists a dialog has (addition articles, matrix values), {tab, items}."""
    page = _page(kind)
    _, html = session._page(page)
    found = _list(html)
    hits = [it for it in found if str(ref) == it["id"]] or \
           [it for it in found if str(ref).lower() == it["name"].lower()]
    if len({it["id"] for it in hits}) != 1:
        raise E37Error(f"{'Flera' if hits else 'Ingen'} post i {REGISTERS[kind][1]} matchar {ref!r}. "
                       f"Lista med: e37 view {kind}")
    it = hits[0]
    data = _form_full(html)
    data.update({"__EVENTTARGET": "__Page", "__EVENTARGUMENT": it["_arg"]})
    _, opened = session._page(page, data)
    dialog = _dialog(opened)
    if dialog is None:
        raise E37Error(f"{REGISTERS[kind][1]}: posten {it['id']} gick inte att öppna")
    dialog.update({"kind": kind, "id": it["id"], "name": it["name"]})
    return dialog


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
        out.append({"id": ident, "name": name, "columns": columns, "notes": notes,
                    "section": section, "parent": pname, "_arg": arg})
    return out


# ---- edit dialog ---------------------------------------------------------------

def _dialog(html):
    root = _dom(html)
    box = root.find(lambda n: "modalpopup" in n.cls.split() and n.find(lambda x: "popupTabContent" in x.cls.split()))
    if box is None:
        return None
    head = box.find(lambda n: "topContent" in n.cls.split())
    tabnames = {}
    for li in box.find_all(lambda n: n.tag == "li" and "popupTabItem|" in n.attrs.get("id", "")):
        tabnames[li.attrs["id"].split("|")[-1]] = li.text()
    labels = {x.attrs["for"]: x.text() for x in box.find_all(lambda x: x.tag == "label" and x.attrs.get("for"))}
    fields, lists = [], []
    for tab in box.find_all(lambda n: "popupTabContent" in n.cls.split()):
        tname = tabnames.get(tab.attrs.get("id", "").split("_")[-1], "")
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
                value = _value(n, labels)
                if value is None or value == "":
                    continue
                name = n.attrs["name"]
                if name.endswith("$cbCheckAll"):
                    continue
                lab = _row_label(n) or label or name.split("$")[-1]
                if value.startswith(lab + ": "):
                    value = value[len(lab) + 2:]
                lang = name.split("$")[-1]
                if re.fullmatch(r"[a-z]{2}", lang) and lang not in lab:
                    lab = f"{lab} [{lang}]"
                fields.append({"tab": tname, "label": lab, "value": value})
    return {"title": head.text() if head else "", "fields": _merge(fields), "lists": lists}


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


def _value(n, labels):
    """What the field shows, or None for fields that are not shown."""
    t = (n.attrs.get("type") or "").lower()
    if n.tag == "select":
        sel = [o.text() for o in n.find_all(lambda o: o.tag == "option" and "selected" in o.attrs)]
        if not sel:
            first = n.find(lambda o: o.tag == "option")
            sel = [first.text()] if first and "multiple" not in n.attrs else []
        return ", ".join(sel)
    if n.tag == "textarea":
        return n.text(raw=True).strip()
    if t in ("hidden", "submit", "image", "button", "file", "password"):
        return None
    if t == "checkbox":
        own = labels.get(n.attrs.get("id"))
        return f"{own}: {'ja' if 'checked' in n.attrs else 'nej'}" if own else ("ja" if "checked" in n.attrs else "nej")
    if t == "radio":
        if "checked" not in n.attrs:
            return None
        return labels.get(n.attrs.get("id")) or n.attrs.get("value", "")
    return unescape(n.attrs.get("value", ""))



def _merge(fields):
    """One entry per label: checkboxes and multi-part fields under one label are joined."""
    out = []
    for f in fields:
        if out and out[-1]["tab"] == f["tab"] and out[-1]["label"] == f["label"] and f["value"] != "":
            out[-1]["value"] = "; ".join(v for v in (out[-1]["value"], f["value"]) if v)
        elif not (out and out[-1]["tab"] == f["tab"] and out[-1]["label"] == f["label"]):
            out.append(dict(f))
    return out


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
