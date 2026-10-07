"""
The public MCP server every E37 shop exposes at /api/mcp.

No key, no session: plain JSON-RPC 2.0 over POST, and `initialize` is not needed
before `tools/call` (docs/mcp.md). It is a production shop all the same, so
nothing here loops or paginates on its own.

The useful payload is not in the text part of the answer. `result.content` holds
a Swedish summary first and then a `resource` whose `text` is a JSON *string*;
`call` returns that, parsed, and the summary alongside.
"""

import json
import os
from urllib import request
from urllib.error import HTTPError, URLError

from . import E37Error, __version__

USER_AGENT = f"e37-cli/{__version__} (+https://github.com/Wesports-Scandinavia-AB/e37-cli)"

SHOPS = {
    "addnature": "https://www.addnature.com/api/mcp",
    "outdoorexperten": "https://www.outdoorexperten.se/api/mcp",
}
DEFAULT_SHOP = "addnature"

SORT_KEYS = ("rank", "latest", "title_asc", "title_desc", "price_asc", "price_desc")


def shop_url(shop=None):
    """A shop name from SHOPS, a full URL, or E37_MCP_URL, in that order."""
    if shop:
        if shop.startswith("http"):
            return shop
        url = SHOPS.get(shop.lower())
        if not url:
            raise E37Error(f"Okänd butik {shop!r}. Kända: {', '.join(SHOPS)}, eller ange en URL.")
        return url
    return os.environ.get("E37_MCP_URL") or SHOPS[DEFAULT_SHOP]


def _rpc(shop, method, params=None, timeout=60):
    url = shop_url(shop)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                      ensure_ascii=False).encode("utf-8")
    # The User-Agent is not decoration: the shops sit behind a filter that answers
    # urllib's default one with 403.
    req = request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            reply = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raise E37Error(f"{method} mot {url}: HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
    except URLError as e:
        raise E37Error(f"Nådde inte {url}: {e.reason}")
    if reply.get("error"):
        raise E37Error(f"{method}: {reply['error'].get('message', reply['error'])}")
    return reply.get("result") or {}


def tools(shop=None):
    """The server's own tool list with input schemas — the truth when docs/mcp.md drifts."""
    return _rpc(shop, "tools/list").get("tools") or []


def call(shop, tool, timeout=60, **arguments):
    """Call one MCP tool. Returns (summary_text, data) where data is parsed JSON or None."""
    result = _rpc(shop, "tools/call",
                  {"name": tool, "arguments": {k: v for k, v in arguments.items() if v is not None}},
                  timeout=timeout)
    summary, data = None, None
    for part in result.get("content") or []:
        if part.get("type") == "text" and summary is None:
            summary = part.get("text")
        elif part.get("type") == "resource":
            text = (part.get("resource") or {}).get("text")
            if text:
                data = json.loads(text)
    return summary, data


def search(shop, query, top=30, brands=None, sort_by=None, in_stock_only=None, campaign_only=None):
    # The server answers a one-character query with HTTP 500 rather than an error.
    if not 2 <= len(query) <= 100:
        raise E37Error("Sökordet måste vara 2–100 tecken.")
    return call(shop, "search_products", query=query, max_nr_of_products=top, brands=brands or None,
                sort_by=sort_by, in_stock_only=in_stock_only, campaign_only=campaign_only)


def product(shop, model_number=None, gtin=None, specifications=False):
    """One product model, or None — an unknown one comes back as empty content, not an error.

    The server prefers `modelNumber`, the identifier shared by every colour and
    size of a model; a GTIN names one variant and is the fallback. Specifications
    (colour, material, weight ...) only come back when asked for.
    """
    return call(shop, "get_product", modelNumber=model_number, gtin=gtin,
                include_specifications=specifications or None)[1]
