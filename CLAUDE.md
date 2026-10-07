# e37-cli

Python-CLI och bibliotek för E37, webbshopsplattformen bakom Cykloteket, Bikester,
Addnature, Outdoorexperten med flera. Byggt som `wsg-cli`: `src/`-layout, bara
standardbiblioteket, argparse, entry point `e37`.

## Regler

- Inga tredjepartsberoenden i kärnan. `urllib` och `json` räcker för Admin-API:t och MCP:n, som båda svarar JSON. Samma beslut som i wsg-cli.
- Undantag: modulen mot E37 Admin-webben (ASP.NET WebForms) använder Scrapling, som det valfria tillägget `e37-cli[web]`. Importera det inne i den modulen, aldrig från `cli.py` på toppnivå, så att `e37 shop` och `e37 order` fungerar utan det. Beslut 2026-10-07.
- Inga hemligheter i repot. Nycklar ligger i miljövariabler eller i `%LOCALAPPDATA%\e37\accounts.json`. Originalet finns i `wesports-secrets`.
- Rapport-endpointen tar nyckeln i URL:en. Skriv aldrig ut en request-URL och bygg aldrig ett felmeddelande av den.
- Språk: dokumentation och utskrifter till användaren på svenska. Kod, kommentarer och `--help` på engelska.
- Dokumentera API-detaljer och beslut i `docs/` allteftersom de blir kända. Rätta `docs/` när ett live-svar säger något annat.

## Struktur

- `src/e37/admin.py`: E37 Admin, alltså orderflödesrapporten (nyckel i query) och Triton Admin REST API (Basic: webshop-ID och nyckel). Läser bara.
- `src/e37/shop.py`: butikens publika MCP-server (`/api/mcp`), JSON-RPC utan auth. Kräver en egen User-Agent; urllibs standard får 403.
- `src/e37/cli.py`: argparse-kommandona. Ingen anropslogik här.
- `docs/`: Order-API, OpenAPI-spec, MCP, webbgränssnittet (`docs/web.md`).

Webbgränssnittet (ASP.NET WebForms) och en egen MCP-server läggs till som moduler i `src/e37/` när de behövs, inte som egna paket.

## Status (2026-10-07)

- `e37 shop` fungerar mot Addnature och Outdoorexperten.
- `e37 order` är byggt efter OpenAPI-specen men aldrig kört med giltig nyckel. Nyckelskapande i E37 Admin felar och Tommy har kontakt med E37. Både `/reports/orderflow` och `/orders/{id}/status` på admin3 svarar 401 på en ogiltig nyckel, så sökvägarna stämmer.
