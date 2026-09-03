# e37

Samlingsrepo för E37-integrationer (API-anrop, MCP-server, dokumentation).

## Regler

- Inga hemligheter i repot. Nycklar och tokens ligger i `.env` (gitignorerad) eller i `wesports-secrets`.
- Dokumentera API-detaljer och beslut i `docs/` allteftersom de blir kända.
- Språk i dokumentation: svenska. Kod och kommentarer i kod: engelska.

## Status

Repot är nystartat (2026-09-03). Detaljer om E37:s API och MCP kommer senare.

## Struktur

- `client/` – typad klient mot E37:s API. All anropslogik mot E37 ligger här.
- `mcp/` – MCP-server. Importerar `client/`, duplicerar inte anrop.
- `docs/` – dokumentation och beslut.

Platt struktur medvetet. Flytta till `packages/` först när ett tredje paket behövs.
