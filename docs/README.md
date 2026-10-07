# docs

Anteckningar om E37: API-endpoints, autentisering, MCP-upplägg och beslut.

| Fil | Innehåll |
|---|---|
| [order-api.md](order-api.md) | E37 Order API: orderflödesrapporten, Triton Admin REST API, statuswebhook, pollningsrecept och öppna frågor. Specen själv finns hos E37: <https://admin3.e37.se/docs/>. |
| [mcp.md](mcp.md) | E37:s publika MCP-server per butik (verktyg, protokoll, svarsformat). |
| [web.md](web.md) | Karta över E37 Admin som webbgränssnitt: inloggning, butiksväljare, artikelregister, variantdialog, luckor i API:et och hur vi bygger `e37 web`. |

## Översikt över E37:s ytor

| Yta | Bas | Auth | Status |
|---|---|---|---|
| Orderflödesrapport | `https://admin3.e37.se/api/reports/orderflow` | API-nyckel som `key`-queryparameter | Live, men vi saknar nyckel |
| Triton Admin REST API | `https://admin3.e37.se/api` (eller admin2) | HTTP Basic, webshop-ID:nyckel | Dokumenterat, ej testat |
| Orderstatus-webhook | E37 POST:ar till vår URL | Registreras i E37 Admin | Ej uppsatt |
| MCP-server | `https://<butik>/api/mcp` | Ingen | Live, testad |
| Webbgränssnitt (E37 Admin) | `https://admin3.e37.se` | Inloggning, ASP.NET WebForms | Se [web.md](web.md) |
