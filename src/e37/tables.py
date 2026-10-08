"""
Read simple two-column lists (article number, date) from Excel or CSV, without
pandas or openpyxl: an .xlsx is a zip of XML, and two columns of one sheet need
nothing more than zipfile and ElementTree.
"""

import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from . import E37Error

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_rows(path):
    """Rows as dicts with lower-cased, stripped header names. Values are strings or dates."""
    p = Path(path)
    if not p.is_file():
        raise E37Error(f"Filen finns inte: {path}")
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        return _xlsx(p)
    raw = p.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(raw.splitlines()[0] if raw else ";", delimiters=";,\t")
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader]


def _xlsx(p):
    with zipfile.ZipFile(p) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        sheet = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
        root = ET.fromstring(z.read(sheet))
    grid = []
    for row in root.iter(f"{{{_NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", _NS):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            v = c.find("m:v", _NS)
            is_ = c.find("m:is", _NS)
            if c.get("t") == "s" and v is not None:
                val = shared[int(v.text)]
            elif c.get("t") == "inlineStr" and is_ is not None:
                val = "".join(t.text or "" for t in is_.iter(f"{{{_NS['m']}}}t"))
            else:
                val = v.text if v is not None else ""
            cells[col] = val
        grid.append(cells)
    if not grid:
        return []
    header = {col: (name or "").strip().lower() for col, name in grid[0].items()}
    return [{header[c]: v for c, v in r.items() if c in header} for r in grid[1:] if any(r.values())]


def as_date(value):
    """'2026-10-09', '2026-10-09 00:00:00' or an Excel serial number -> 'YYYY-MM-DD'."""
    s = str(value or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        # Excel counts days from 1899-12-30 (the 1900 leap-year bug included).
        return (date(1899, 12, 30) + timedelta(days=int(float(s)))).isoformat()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise E37Error(f"Förstår inte datumet {s!r}. Använd ÅÅÅÅ-MM-DD.")


def article_rows(path):
    """[(art_nr, date or None)] from a file with columns art-nr and (optionally) datum."""
    rows = read_rows(path)
    if not rows:
        raise E37Error(f"{path} är tom.")
    keys = set(rows[0])
    art_key = next((k for k in ("art-nr", "artnr", "artikelnummer", "art_nr", "sku") if k in keys), None)
    if not art_key:
        raise E37Error(f"{path} saknar kolumnen 'art-nr'. Hittade: {', '.join(sorted(keys))}")
    date_key = next((k for k in ("datum", "date") if k in keys), None)
    out = []
    for r in rows:
        art = str(r.get(art_key) or "").strip()
        if art.endswith(".0"):
            art = art[:-2]   # a number cell read back as float text
        if art:
            out.append((art, as_date(r.get(date_key)) if date_key else None))
    return out
