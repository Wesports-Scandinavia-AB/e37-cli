"""
Article attribute values per variant, such as the campaign attribute Kampanj
(#CAMPAIGN) that E37 turns into campaign tags ("#campaign y26midfastpris") which
campaign pages' product lists show. Mapped and verified 2026-10-09; see docs/web.md.

READ through E37's own export (Artikelattribut → Exportera artikelattribut), which
is a GET to /custom/exporthandler.ashx?Type=ATTRIBUTES. It returns E37's Excel
template: four header rows (Typ, Språk, Namn, Importnyckel), then one row per
variant with the variant's article number in column A, the main article number in
C, and one column per value of a multi-value attribute.

WRITE through E37's own import (Import → Artikelattribut), with a sheet in that same
format and import type 3, "Partiell import (lägg till/uppdatera vissa kombinationer
av artiklar och attribut)": only the variant and attribute combinations in the sheet
are touched. Types 1 and 2 replace or delete other articles' attributes and are
never used. Every import is proven by exporting the attribute in full before and
after: only the given variants may have changed, and each exactly as planned.
"""

import io
import re
import uuid
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from . import E37Error

EXPORT = "custom/exporthandler.ashx?Type=ATTRIBUTES&langCode={lang}&attrTypesIds={attr};"
IMPORT_PAGE = "workspace/workwith/articles/attributesImport.aspx"
ARTICLES = "workspace/workwith/articles/list.aspx"
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PARTIAL_COMBINATIONS = "rbImportTypePartial3"


def values(session, attr_id, lang="sv"):
    """(header, {variant nr: {"main", "title", "values": [...]}}) for every variant that
    has a value of the attribute, from E37's export. header is the four template rows
    of the attribute's columns, as the import wants them back."""
    with session._open(EXPORT.format(lang=lang, attr=int(attr_id))) as resp:
        body = resp.read()
    if body[:2] != b"PK":
        raise E37Error("E37:s export av artikelattribut gav ingen Excel-fil")
    rows = _sheet(body)
    if len(rows) < 4 or rows[0].get("A", "").rstrip(":") != "Typ":
        raise E37Error("E37:s attributexport har ett okänt format")
    cols = [c for c, v in rows[3].items() if v.startswith("#")]
    if not cols:
        raise E37Error(f"attributet {attr_id} finns inte i exporten")
    header = {"type": rows[0][cols[0]], "lang": rows[1].get(cols[0], ""), "name": rows[2][cols[0]],
              "key": rows[3][cols[0]]}
    out = {}
    for r in rows[4:]:
        art = r.get("A", "").strip()
        if art:
            out[art] = {"main": r.get("C", ""), "title": r.get("B", ""),
                        "values": [r[c] for c in cols if r.get(c, "").strip()]}
    return header, out


def variants(session, art_nr):
    """{variant nr: main nr} for a main or variant article number, from the article
    register's search (variant rows follow their main row)."""
    from .web import _form_full
    _, page = session._page(ARTICLES)
    data = _form_full(page)
    data.update({"ctl00$cph1$settingstabs$tabSearch$txtSearch": art_nr,
                 "ctl00$cph1$settingstabs$tabSearch$btnArticleSearch.x": "5",
                 "ctl00$cph1$settingstabs$tabSearch$btnArticleSearch.y": "5"})
    _, html = session._page(ARTICLES, data)
    out, main = {}, None
    for m in re.finditer(r'<tr[^>]*?(?:data-article-main-nr="([^"]*)"|data-article-variant-nr="([^"]*)")', html):
        if m.group(1) is not None:
            main = m.group(1)
        elif main is not None:
            out[m.group(2)] = main
    hits = {v: mn for v, mn in out.items() if mn == art_nr} or {v: mn for v, mn in out.items() if v == art_nr}
    if not hits:
        raise E37Error(f"hittade ingen artikel med exakt artikelnummer {art_nr}")
    return hits


def set_values(session, attr_id, changes, apply=False, update_tags=False, waits=6, wait_seconds=10):
    """changes is {variant nr: [values]}: the attribute's full set of values for each
    variant after the import. Returns [{variant, main, old, new}] for those that change.
    With apply the sheet is imported with import type 3 and proven by a full export."""
    header, before = values(session, attr_id)
    plan = []
    for v, new in changes.items():
        old = before.get(v, {}).get("values", [])
        if sorted(old) != sorted(new):
            plan.append({"variant": v, "main": before.get(v, {}).get("main", ""), "old": old, "new": new})
    if not apply or not plan:
        return plan, False
    sheet = _workbook(header, {p["variant"]: p["new"] for p in plan})
    message = _upload(session, sheet, update_tags)
    wanted = {p["variant"]: sorted(p["new"]) for p in plan}
    # The import may finish after the page answers; export again for a while before
    # judging, but judge every variant either way.
    import time
    for attempt in range(waits + 1):
        _, after = values(session, attr_id)
        if all(sorted(after.get(v, {}).get("values", [])) == new for v, new in wanted.items()) or attempt == waits:
            break
        time.sleep(wait_seconds)
    moved = sorted(v for v in set(before) | set(after)
                   if v not in wanted and sorted(before.get(v, {}).get("values", []))
                   != sorted(after.get(v, {}).get("values", [])))
    if moved:
        raise E37Error(f"ANDRA ARTIKLAR ÄNDRADES vid importen: {', '.join(moved[:10])}"
                       f"{' …' if len(moved) > 10 else ''}. Kontrollera i E37 Admin. E37 sa: {message}")
    wrong = [v for v, new in wanted.items() if sorted(after.get(v, {}).get("values", [])) != new]
    if wrong:
        raise E37Error(f"importen gav inte de planerade värdena för {', '.join(wrong[:10])}. "
                       f"E37 sa: {message}")
    return plan, True


def _upload(session, xlsx, update_tags):
    """The import page's own three steps: choose the import type (a postback), send the
    file to /custom/fileuploadhandler.ashx under the page's cacheKey, then press Ladda
    upp on that same page, which takes the file from the cache. Returns what E37 says."""
    from urllib import request
    from .web import USER_AGENT, _form_full
    from .registers import _message
    _, page = session._page(IMPORT_PAGE)
    data = _form_full(page)
    data.update({"ctl00$cph1$ImportType": PARTIAL_COMBINATIONS,
                 "__EVENTTARGET": "ctl00$cph1$" + PARTIAL_COMBINATIONS, "__EVENTARGUMENT": ""})
    _, page = session._page(IMPORT_PAGE, data)
    if not re.search(r'value="%s"[^>]*checked|checked[^>]*value="%s"' % (PARTIAL_COMBINATIONS, PARTIAL_COMBINATIONS), page):
        raise E37Error("importtyp 3 gick inte att välja, avbryter")
    key = re.search(r'type="file"[^>]*data-cacheKey="([0-9A-F]+)"', page, re.I)
    if not key:
        raise E37Error("hittade inget filfält med cacheKey på importsidan")

    boundary = "----e37cli" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="e37-attribut.xlsx"; filename="e37-attribut.xlsx"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode() \
        + xlsx + f"\r\n--{boundary}--\r\n".encode()
    req = request.Request(f"{session.base}custom/fileuploadhandler.ashx?cacheKey={key.group(1)}"
                          "&uploadType=fileupload&overwriteOnConflict=false", data=body,
                          headers={"User-Agent": USER_AGENT, "Content-Type": f"multipart/form-data; boundary={boundary}",
                                   "X-Requested-With": "XMLHttpRequest"})
    with session._op.open(req, timeout=max(session.timeout, 300)) as resp:
        resp.read()

    data = _form_full(page)
    data["ctl00$cph1$ImportType"] = PARTIAL_COMBINATIONS
    data.pop("ctl00$cph1$cbDeleteExcludedAttributes", None)   # never: deletes other attributes
    if update_tags:
        data["ctl00$cph1$cbDoUpdateGenTags"] = "on"
    else:
        data.pop("ctl00$cph1$cbDoUpdateGenTags", None)
    data["ctl00$cph1$btnUpload.x"], data["ctl00$cph1$btnUpload.y"] = "5", "5"
    _, done = session._page(IMPORT_PAGE, data)
    said = _message(done) or ""
    if "Är du säker" in said:
        # E37 restates the import type and asks. Confirm only the one we chose.
        if "Partiell import" not in said or "Utelämnade artiklar och utelämnade attribut påverkas ej" not in said:
            raise E37Error(f"E37 bad om bekräftelse på något annat än importtyp 3, avbryter: {said}")
        ok = re.search(r'name="(ctl00\$cph1\$msgBox_panel\$msgBox_btnOK)"[^>]*type="(\w+)"|'
                       r'type="(\w+)"[^>]*name="(ctl00\$cph1\$msgBox_panel\$msgBox_btnOK)"', done)
        if not ok:
            raise E37Error("hittade inte OK-knappen i E37:s fråga, avbryter")
        data = _form_full(done)
        button = "ctl00$cph1$msgBox_panel$msgBox_btnOK"
        if (ok.group(2) or ok.group(3)) == "image":
            data[button + ".x"], data[button + ".y"] = "5", "5"
        else:
            data[button] = "OK"
        _, done = session._page(IMPORT_PAGE, data)
        said = _message(done) or ""
    process = re.search(r'id="ctl00_cph1_timeProcess"[^>]*>([^<]*)<', done)
    return " ".join(x for x in (said, process.group(1).strip() if process else "") if x)


def _workbook(header, rows):
    """A one-sheet xlsx in E37's attribute template: column A the variant number, then
    one column per value, with the attribute's four header rows."""
    width = max([1] + [len(v) for v in rows.values()])
    cols = [_col(i) for i in range(2, 2 + width)]

    def cell(ref, text):
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'
    lines = []
    for n, (label, key) in enumerate((("Typ:", "type"), ("Språk:", "lang"), ("Namn:", "name"),
                                      ("Importnyckel:", "key")), 1):
        lines.append(f'<row r="{n}">' + cell(f"A{n}", label)
                     + "".join(cell(f"{c}{n}", header[key]) for c in cols if header[key]) + "</row>")
    for n, (variant, vals) in enumerate(rows.items(), 5):
        lines.append(f'<row r="{n}">' + cell(f"A{n}", variant)
                     + "".join(cell(f"{c}{n}", v) for c, v in zip(cols, vals)) + "</row>")
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + "".join(lines) + "</sheetData></worksheet>")
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>",
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>",
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Attribut" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>",
        "xl/worksheets/sheet1.xml": sheet,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _sheet(body):
    """The first sheet of an xlsx as [{column letter: text}]."""
    z = zipfile.ZipFile(io.BytesIO(body))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in root.iter(f"{{{_NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", _NS):
            col = re.match(r"[A-Z]+", c.get("r", "")).group(0)
            v, isv = c.find("m:v", _NS), c.find("m:is", _NS)
            if c.get("t") == "s" and v is not None:
                cells[col] = shared[int(v.text)]
            elif c.get("t") == "inlineStr" and isv is not None:
                cells[col] = "".join(t.text or "" for t in isv.iter(f"{{{_NS['m']}}}t"))
            else:
                cells[col] = v.text if v is not None and v.text else ""
        rows.append(cells)
    return rows
