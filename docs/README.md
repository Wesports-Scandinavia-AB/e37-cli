# docs

Anteckningar om E37: API-endpoints, autentisering, MCP-upplägg och beslut.

| Fil | Innehåll |
|---|---|
| [order-api.md](order-api.md) | E37 Order API: orderflödesrapporten, Triton Admin REST API, statuswebhook, pollningsrecept, kända butiker och öppna frågor till E37. Sammanställd 2026-09-03. |
| [order-api.pdf](order-api.pdf) | Samma dokument som PDF. |
| [triton-admin-1.0.openapi.json](triton-admin-1.0.openapi.json) | OpenAPI 3.1-spec för Triton Admin REST API, hämtad från `https://admin3.e37.se/docs/Triton-Admin-1.0.json` 2026-09-03. |
| [mcp.md](mcp.md) | E37:s publika MCP-server per butik (verktyg, protokoll, svarsformat). |
| [mcp-chat-test.md](mcp-chat-test.md) | Test av att chatta om produkter via MCP:n på Addnature. Vad som fungerar, vad som inte gör det, och vad vår egen MCP behöver kompensera för. |

## Översikt över E37:s ytor

| Yta | Bas | Auth | Status |
|---|---|---|---|
| Orderflödesrapport | `https://admin3.e37.se/api/reports/orderflow` | API-nyckel som `key`-queryparameter | Live, men vi saknar nyckel |
| Triton Admin REST API | `https://admin3.e37.se/api` (eller admin2) | HTTP Basic, webshop-ID:nyckel | Dokumenterat, ej testat |
| Orderstatus-webhook | E37 POST:ar till vår URL | Registreras i E37 Admin | Ej uppsatt |
| MCP-server | `https://<butik>/api/mcp` | Ingen | Live, testad |
| Webbgränssnitt (E37 Admin) | `https://admin3.e37.se` | Inloggning, ASP.NET WebForms | Se `client/web/` |
