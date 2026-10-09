# e37-cli

Python-CLI och bibliotek för E37, webbshopsplattformen bakom Cykloteket, Bikester,
Addnature, Outdoorexperten med flera. Byggt som `wsg-cli`: `src/`-layout, bara
standardbiblioteket, argparse, entry point `e37`.

## Regler

- Inga tredjepartsberoenden i kärnan. `urllib` och `json` räcker för Admin-API:t och MCP:n, som båda svarar JSON. Samma beslut som i wsg-cli.
- Undantag: behöver en webbsida en riktig webbläsare används Scrapling, som det valfria tillägget `e37-cli[web]`, importerat i den funktion som behöver det. Hittills (2026-10-07) har allt i `web.py` gått med `urllib`.
- Vägval: API:t bara för det API:t kan svara på och bara när kontot har nyckel. Annars personens webbinloggning. E37:s API har nästan ingenting; webben är huvudvägen.
- Inga hemligheter i repot eller i filer. E37-inloggningar är personliga och ligger i användarens nyckelring via `src/e37/keychain.py`: Credential Manager på Windows, nyckelringen på macOS. Inte i Arena-valvet, som är för bolagets maskinhemligheter. Miljövariabler `E37_*` går före, för CI.
- Ett hemligt värde passerar aldrig argv. Det läses med `getpass` eller från stdin. På macOS skrivs det via `security -i` och stdin, hex-kodat.
- Flera E37-instanser används samtidigt (olika webbshop-ID, olika bolag). Ingen global state och ingen standardinstans. Allt går via ett konto från `admin.resolve_account` (en nyckelringspost per instans), och webbsessioner delas aldrig mellan körningar. Se "Flera instanser samtidigt" i `docs/web.md`.
- Rapport-endpointen tar nyckeln i URL:en. Skriv aldrig ut en request-URL och bygg aldrig ett felmeddelande av den.
- Språk: dokumentation och utskrifter till användaren på svenska. Kod, kommentarer och `--help` på engelska.
- Dokumentera API-detaljer och beslut i `docs/` allteftersom de blir kända. Rätta `docs/` när ett live-svar säger något annat.

## Struktur

- `src/e37/admin.py`: E37 Admin, alltså orderflödesrapporten (nyckel i query) och Triton Admin REST API (Basic: webshop-ID och nyckel). Läser bara.
- `src/e37/shop.py`: butikens publika MCP-server (`/api/mcp`), JSON-RPC utan auth. Kräver en egen User-Agent; urllibs standard får 403.
- `src/e37/web.py`: E37 Admin med personens egen inloggning: login, webbplatser, rapporter via `/custom/orderReportHandler.ashx`. Bara standardbiblioteket; inget har behövt en webbläsare än. Läser bara.
- `src/e37/registers.py`: `e37 view`, marknadsregistren i E37 Admin (kampanjer, rabattkoder, taggar, attribut, sidor, innehållselement, widgets, tillval, matriser). Läser bara. Postbacken som öppnar en post tar också bort och kopierar, så argumentet tas från postens egen länk och bara för funktionerna i `_OPENERS`.
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
- Via webbinloggningen, verifierat mot en riktig instans: inloggning, `sites`, `order flow`, `order show/status` (orderrutan tolkad från HTML) och `report list/show/get`.
- Via webbinloggningen, verifierat 2026-10-09: `view` för de nio marknadsregistren. Det som inte kommer med än (attributvärden, matrisvärden, sidornas och widgetarnas innehåll) står i `docs/web.md`. Skrivningarna marknad har bett om (kampanjer, rabattkoder, badger, kampanjsidor, topprodukter, tillvalsbyte, storlekssortering) är inte byggda.
- Via API:t: allt är byggt efter OpenAPI-specen men aldrig kört med giltig nyckel.
- Skriver: `delivery-text set --apply`, verifierat 2026-10-08 mot en riktig variant (satt, kontrollerat, tömt). Texten är per språk; alla sv-webbplatser delar fältet.
- Skriver: `additions swap --apply`, verifierat 2026-10-09 på en uppsättning utan artiklar (bytt och tillbaka). Inbäddade dialogens Spara sparar direkt; borttag kräver ytterdialogens Spara.
- Skriver: `change --apply` (fält i marknadsregistren), verifierat 2026-10-09 på en tagg utan artiklar och en inaktiv kampanj (satt, kontrollerat, återställt). `…$usrCtrl$isPostback` måste postas som `1`, annars försvinner ändringen tyst; se `docs/web.md`.
- Provskrivningar mot E37 görs bara på poster som kunder inte ser (inaktiva kampanjer och koder, taggar utan artiklar, sidan AA-test) och återställs alltid.
- Regler för allt som skriver: torrkörning som standard och `--apply` för att spara; hela formuläret serialiseras som en webbläsare gör (`_form_full`: textarea, multi-select, inga disabled); efter sparning öppnas posten igen och ALLA fält jämförs, och något oväntat ändrat stoppar körningen; logg med gammalt och nytt värde.
- Orderrutan har knappar som ändrar ordern (aktivera, makulera, byt leveranssätt, skicka bekräftelse, orderstatus). `web.py` skickar bara postbacken som öppnar rutan. Lägg aldrig till något som postar de knapparna utan ett eget kommando med `--dry-run`.
