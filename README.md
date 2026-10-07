# e37

Ordrar och produkter ur webbshopsplattformen E37 (Cykloteket, Bikester, Addnature,
Outdoorexperten med flera), från terminalen eller från ett skript. Två ytor:

- `e37 order`: E37 Admin, alltså orderflödesrapporten och Triton Admin REST API. Kräver API-nyckel.
- `e37 shop`: butikens publika MCP-server med produkter, varumärken, kategorier och taggar. Ingen nyckel.

## Installera

```
pipx install git+https://github.com/Wesports-Scandinavia-AB/e37-cli
```

eller för utveckling:

```
git clone https://github.com/Wesports-Scandinavia-AB/e37-cli
pip install -e e37-cli
```

Kräver Python 3.9+. Inga tredjepartsberoenden.

## Använd

```
e37 accounts             konfigurerade butiker (aldrig nyckeln)

e37 order flow           orderflödesrapporten, föregående stängda halvtimme
e37 order flow --from '2026-10-07 08:00' --to '2026-10-07 09:00'
e37 order show ID        en order i sin helhet: kund, betalning, leverans, rader
e37 order status ID      en orders aktuella status

e37 shop search ORD      produktsök, --top, --brand, --sort, --in-stock, --campaign
e37 shop product NR      en produktmodell via modellnummer (--gtin för variant), --specs
e37 shop brands          varumärken med antal produkter
e37 shop categories      toppkategorier
e37 shop tags            taggar, två nivåer
e37 shop tools           serverns egen verktygslista med argument
```

Alla kommandon tar `--json` för rådata. `--shop addnature|outdoorexperten|<URL>`
väljer butik för `shop`; standard är `$E37_MCP_URL`, annars Addnature.

## Nycklar

`e37 order` läser butikerna i den här ordningen:

1. Miljövariabler för en butik: `E37_ACCOUNT`, `E37_WEBSHOP_ID`, `E37_API_KEY`,
   valfritt `E37_ADMIN_BASE_URL` (standard `https://admin3.e37.se/api`).
2. `%LOCALAPPDATA%\e37\accounts.json` (eller `~/.config/e37/accounts.json`,
   eller sökvägen i `E37_CONFIG`):

```json
{"accounts": [
  {"name": "cykloteket", "webshopId": "…", "key": "…"},
  {"name": "bikester", "account": "…", "webshopId": "…", "key": "…", "baseUrl": "https://admin2.e37.se/api"}
]}
```

`account` är E37:s slug för rapporten och är som standard samma som `name`.
`webshopId` behövs bara för REST-API:t (`show`, `status`). Nyckeln checkas aldrig
in. Originalet ligger i `wesports-secrets`.

## Dokumentation

Se `docs/README.md`: Order-API, OpenAPI-spec, MCP-servern och anteckningar om webbgränssnittet.

## Från Python

```python
from e37 import admin, shop
acc = admin.resolve_account("cykloteket")
rows = admin.orderflow(acc, *admin.half_hour_window())
summary, data = shop.search("addnature", "regnjacka", top=5)
```
