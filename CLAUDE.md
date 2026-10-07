# e37-cli

Python-CLI och bibliotek för E37, webbshopsplattformen bakom Cykloteket, Bikester,
Addnature, Outdoorexperten med flera. Byggt som `wsg-cli`: `src/`-layout, bara
standardbiblioteket, argparse, entry point `e37`.

## Regler

- Inga tredjepartsberoenden i kärnan. `urllib` och `json` räcker för Admin-API:t och MCP:n, som båda svarar JSON. Samma beslut som i wsg-cli.
- Undantag: modulen mot E37 Admin-webben (ASP.NET WebForms) använder Scrapling, som det valfria tillägget `e37-cli[web]`. Importera det inne i den modulen, aldrig från `cli.py` på toppnivå, så att `e37 shop` och `e37 order` fungerar utan det. Beslut 2026-10-07.
- Inga hemligheter i repot eller i filer. E37-inloggningar är personliga och ligger i användarens nyckelring via `src/e37/keychain.py`: Credential Manager på Windows, nyckelringen på macOS. Inte i Arena-valvet, som är för bolagets maskinhemligheter. Miljövariabler `E37_*` går före, för CI.
- Ett hemligt värde passerar aldrig argv. Det läses med `getpass` eller från stdin. På macOS skrivs det via `security -i` och stdin, hex-kodat.
- Flera E37-instanser används samtidigt (olika webbshop-ID, olika bolag). Ingen global state och ingen standardinstans. Allt går via ett konto från `admin.resolve_account` (en nyckelringspost per instans), och webbsessioner delas aldrig mellan körningar. Se "Flera instanser samtidigt" i `docs/web.md`.
- Rapport-endpointen tar nyckeln i URL:en. Skriv aldrig ut en request-URL och bygg aldrig ett felmeddelande av den.
- Språk: dokumentation och utskrifter till användaren på svenska. Kod, kommentarer och `--help` på engelska.
- Dokumentera API-detaljer och beslut i `docs/` allteftersom de blir kända. Rätta `docs/` när ett live-svar säger något annat.

## Struktur

- `src/e37/admin.py`: E37 Admin, alltså orderflödesrapporten (nyckel i query) och Triton Admin REST API (Basic: webshop-ID och nyckel). Läser bara.
- `src/e37/shop.py`: butikens publika MCP-server (`/api/mcp`), JSON-RPC utan auth. Kräver en egen User-Agent; urllibs standard får 403.
- `src/e37/keychain.py`: OS-nyckelringen, en post per E37-instans. Windows via ctypes/advapi32, macOS via `/usr/bin/security`.
- `src/e37/dialog.py`: fönstret för `e37 account add --dialog` (tkinter, med osascript som reserv på macOS). Hemligheter matas in av människan, aldrig via en assistent.
- `src/e37/cli.py`: argparse-kommandona. Ingen anropslogik här.
- `docs/`: Order-API, MCP, webbgränssnittet (`docs/web.md`).
- `src/e37/skill/SKILL.md`: skillen som `e37 skill install` och `e37 update` lägger i `~/.claude/skills/e37/`. Den är den enda beskrivningen av hur en assistent använder `e37`. Ändras ett kommando, ändra skillen i samma commit.
- `INSTALL-FOR-CLAUDE.md`: bara installationen, sedan pekar den på skillen. Upprepa inte kommandoreferensen där.

Versionen står bara i `src/e37/__init__.py` (`pyproject.toml` läser den därifrån). Höj den vid varje ändring som användare märker, så att `e37 update` visar att något hänt.

Repot är publikt. Interna anteckningar (korrespondens, leverantörsbedömningar, underlag från andra bolag) hör hemma i det privata `e37-notes`, inte här.

Webbgränssnittet (ASP.NET WebForms) och en egen MCP-server läggs till som moduler i `src/e37/` när de behövs, inte som egna paket.

## Status (2026-10-07)

- `e37 shop` fungerar mot Addnature och Outdoorexperten.
- `e37 order` är byggt efter OpenAPI-specen men aldrig kört med giltig nyckel. Både `/reports/orderflow` och `/orders/{id}/status` på admin3 svarar 401 på en ogiltig nyckel, så sökvägarna stämmer.
