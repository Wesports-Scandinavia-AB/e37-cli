"""e37: orders and products out of the E37 webshop platform.

    from e37 import admin, shop
    admin.order(admin.resolve_account("cykloteket"), 1189437)   # Triton Admin REST API
    shop.call("addnature", "search_products", query="jacka")   # the public shop MCP
"""

__version__ = "0.9.0"


class E37Error(Exception):
    """Anything the user can act on: missing config, rejected key, unreachable host."""


from . import admin, shop  # noqa: E402,F401
