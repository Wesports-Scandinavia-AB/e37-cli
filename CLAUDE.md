# e37

Samlingsrepo för E37-integrationer (API-anrop, MCP-server, dokumentation).

## Regler

- Inga hemligheter i repot. Nycklar och tokens ligger i `.env` (gitignorerad) eller i `wesports-secrets`.
- Dokumentera API-detaljer och beslut i `docs/` allteftersom de blir kända.
- Språk i dokumentation: svenska. Kod och kommentarer i kod: engelska.

## Status

Repot är nystartat (2026-09-03). E37 är webbshopsplattformen bakom addnature.com och outdoorexperten.se. Deras publika MCP-server är dokumenterad i `docs/mcp.md`. Order-API:t (orderflödesrapport, Triton Admin REST API, webhook) i `docs/order-api.md` med OpenAPI-spec bredvid. API-nyckel saknas ännu; nyckelskapande i E37 Admin felar och Tommy har kontakt med E37.

## Struktur

- `client/api/` – typad klient mot E37:s officiella API. Föredra alltid denna.
- `client/web/` – klient mot E37:s webbgränssnitt, bara för luckor i API:et. Webben är ASP.NET WebForms (ViewState, POST-backs, inga JSON-endpoints); se `client/web/README.md`. Skör; dokumentera vilken lucka varje funktion täcker.
- `mcp/` – MCP-server. Importerar `client/`, duplicerar inte anrop.
- `docs/` – dokumentation och beslut.

Platt struktur medvetet. Flytta till `packages/` först när ett tredje paket behövs.
