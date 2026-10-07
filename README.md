# e37

Ordrar och produkter ur webbshopsplattformen E37 (Cykloteket, Bikester, Addnature,
Outdoorexperten med flera), från terminalen eller från ett skript. Två ytor:

- `e37 order`: E37 Admin, alltså orderflödesrapporten och Triton Admin REST API. Kräver API-nyckel.
- `e37 shop`: butikens publika MCP-server med produkter, varumärken, kategorier och taggar. Ingen nyckel.

## Via Claude

Kollegor som inte använder terminalen kan låta Claude göra allt. Öppna Claude-appen,
välj **Code**, och skriv:

> Läs https://github.com/Wesports-Scandinavia-AB/e37-cli/blob/main/INSTALL-FOR-CLAUDE.md
> och hjälp mig installera e37-cli och lägga till mitt E37-konto.

Claude installerar, och öppnar ett fönster där du själv fyller i dina E37-uppgifter.
Claude ser dem aldrig. Sedan kan du fråga Claude saker som "vilka ordrar kom in
i förmiddags?".

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
e37 account list         dina E37-instanser (aldrig nycklarna), add/remove

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

## Konton och nycklar

E37-inloggningar är personliga: en API-nyckel någon skapat, och e-post och lösenord
till ett eget adminkonto. De sparas därför i din egen nyckelring, aldrig i en fil
och aldrig i repot:

- **Windows:** Credential Manager (`e37-cli:<namn>` under Windows-autentiseringsuppgifter)
- **macOS:** nyckelringen (tjänst `e37-cli`, konto `<namn>`)

En post per E37-instans. Flera instanser, även från olika bolag, kan ligga sida vid sida.

```
e37 account add vartex-outdoor    frågar efter webbshop-ID, API-bas, rapport-slug,
                                  API-nyckel och webbinloggning; Enter behåller värdet
e37 account add vartex-outdoor --dialog
                                  samma sak i ett fönster, för den som inte vill ha terminal
e37 account list                  instanserna, och vilka hemligheter som finns (aldrig värdena)
e37 account remove vartex-outdoor
```

Hemligheter matas in dolt och hamnar aldrig i argv eller skalhistoriken. För
skript går det att pipa in posten som JSON:

```
{"webshopId": "…", "baseUrl": "https://admin2.e37.se/api", "account": "…",
 "key": "…", "web": {"email": "…", "password": "…"}}
```

Allt utom namnet är valfritt. Rapporten behöver `key`, REST-API:t även `webshopId`,
och webbgränssnittet `web`. `account` är E37:s slug för rapporten och är som
standard samma som namnet.

För CI eller ett engångsskript går miljövariabler före nyckelringen: `E37_ACCOUNT`,
`E37_WEBSHOP_ID`, `E37_API_KEY` och valfritt `E37_ADMIN_BASE_URL`.

## Dokumentation

Se `docs/README.md`: Order-API, OpenAPI-spec, MCP-servern och anteckningar om webbgränssnittet.

## Från Python

```python
from e37 import admin, shop
acc = admin.resolve_account("cykloteket")
rows = admin.orderflow(acc, *admin.half_hour_window())
summary, data = shop.search("addnature", "regnjacka", top=5)
```
