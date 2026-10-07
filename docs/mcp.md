# E37:s MCP-server

E37 är webbshopsplattformen bakom bland annat addnature.com och outdoorexperten.se (sessionscookien heter `e37webshopSession`, bilder ligger på `cdn37.se`). Varje butik exponerar en egen MCP-server på samma sökväg.

Undersökt 2026-09-03. Schemat har ändrats sedan dess, se [Ändringar 2026-10-07](#ändringar-2026-10-07). `e37 shop tools` visar vad servern säger just nu.

## Endpoints

| Butik | URL | serverInfo.name |
|---|---|---|
| Addnature SE | `https://www.addnature.com/api/mcp` | Addnature SE |
| OutdoorExperten SE | `https://www.outdoorexperten.se/api/mcp` | OutdoorExperten SE |

Båda kör version `1.96.9742`, organisation "Vartex AB", och har identiska verktyg och scheman. Rimligt antagande: alla E37-butiker har `/api/mcp`.

## Protokoll

- Transport: HTTP POST med JSON-RPC 2.0 i body. `GET` på endpointen ger 404.
- Servern svarar `protocolVersion: 2024-11-05` oavsett vad klienten begär.
- Inget `Mcp-Session-Id`-header krävs. Varje request är fristående; `initialize` behöver inte anropas före `tools/list` eller `tools/call`.
- Ingen autentisering. Öppen och publik.
- Capabilities: bara `tools`. Inga resources eller prompts.
- Skicka body som UTF-8-bytes. Sökningar med å/ä/ö fungerar. (HTTP 500 `{"message":"An error has occurred."}` uppstod vid tester när Git Bash på Windows kodade `-d`-strängen fel, inte på grund av servern.)

## Verktyg

Alla har `language_code` (enum: bara `sv`, default `sv`) och de flesta `country_code` (enum: bara `SE`, default `SE`).

| Verktyg | Argument | Beskrivning |
|---|---|---|
| `search_products` | `query`* (2–100 tecken), `max_nr_of_products` (default 30, max 100), `categories[]`, `brands[]`, `tags[]`, `sort_by`, `in_stock_only`, `campaign_only`, `price_range` | Produktsök. `price_range` är enligt schemat "not implemented". |
| `get_product` | `sku`* | Produktdetaljer. Okänd SKU ger tomt `content`, inte fel. |
| `list_categories` | – | Toppkategorier (11 st på Addnature). |
| `list_brands` | – | Alla varumärken med antal produkter. |
| `list_tags` | – | Taggar. |

`sort_by`: `rank` (default), `latest`, `sku_asc`, `title_asc`, `title_desc`, `price_asc`, `price_desc`.

`categories` och `brands` filtreras på **titel**, `tags` på **nyckel**. Ta värdena från list-verktygen eller från `categories`/`brands`/`tags` i ett tidigare sökresultat.

## Svarsformat

`result.content` innehåller två poster:

1. `{"type":"text","text":"..."}` – svensk sammanfattning, t.ex. "Sökningen på 'jacka' gav totalt 550 produkter, varav 527 är tillåtna att köpa och 60 är på kampanj. Endast 2 produkter returnerades."
2. `{"type":"resource","resource":{"uri":"...","mimeType":"application/json","text":"<JSON-sträng>"}}` – den strukturerade datan. **Observera att JSON:en ligger som en sträng i `text` och måste parsas.**

URI:er: `products://search?q=<query>`, `products://<sku>`, `categories://current`, `brands://current`, `tags://current`.

### search_products

```json
{
  "returned_product_count": 1,
  "total_product_count": 550,
  "total_products_in_stock_count": 527,
  "total_products_on_campaign_count": 60,
  "products": [ { ...produkt } ],
  "categories": [ ... ],
  "brands": [ ... ],
  "tags": [ ... ]
}
```

### Produkt (samma form i sök och get_product)

| Fält | Typ | Exempel |
|---|---|---|
| `sku` | string | `"141637"` |
| `title` | string | `"Sail Racing W Spray Down Hood"` |
| `brand` | string | `"Sail Racing"` |
| `description` | string | Fritext, kan innehålla `\r\n` och HTML-entiteter (`&amp;`) |
| `url` | string | `https://www.addnature.com/sv/articles/2.4019.9174/...` |
| `image_url` | string | `https://03.cdn37.se/qqj/images/...` |
| `price` | string | `"1 530 kr"` – formaterad text, inte tal |
| `currency` | string | `"SEK"` |
| `in_stock` | bool | |
| `is_new` | bool | |
| `is_campaign` | bool | |
| `variations` | array | Bara i sökresultat, saknas i `get_product`. Element: `{"title":"Carbon","in_stock":true}`. Titeln är oftast färg. Ingen egen SKU eller pris per variant. |

### Facetter i sökresultat

`categories`, `brands` och `tags` i sökresultatet är facetter för den aktuella sökningen, med antal träffar per värde. De kan skickas tillbaka som filter i nästa sökning.

- `categories`: `[{"id":4780,"title":"Kläder","nr_of_products":550}]` – filtrera på `title`.
- `brands`: `[{"id":305,"title":"2117 of Sweden","nr_of_products":17}]` – filtrera på `title`.
- `tags`: hierarkiska, två nivåer. Filtrera på `key` från barnen:

```json
{"key":"#GENDER","title":"Målgrupp","nr_of_products":31,"children":[
  {"key":"#gender dam","title":"Dam","nr_of_products":273},
  {"key":"#gender herr","title":"Herr","nr_of_products":280}
]}
```

### list_categories

`[{"id":4780,"title":"Kläder","url":"...","image_url":"..."}]` (`image_url` saknas ibland).

### list_brands

`[{"id":305,"title":"2117 of Sweden","url":"...","nr_of_products":77}]`

### list_tags

157 taggar på Addnature. Samma tvånivåstruktur som i sökresultatet men utan `nr_of_products`. Nycklar är fritext, ibland med `#`-prefix (`#GENDER`, `#gender dam`), ibland bara ett namn (`Pjäxkvalitet klassiska`). Barn kan ha `url`.

`[{"key":"Pjäxkvalitet klassiska","title":"Pjäxkvalitet klassiska","children":[{"key":"Klassiska pjäxor Sportlov","title":"..."},{"key":"...","title":"...","url":"https://www.addnature.com/sv/tag/bra-battre-pjaxor"}]}]`

## Kända brister

Sett vid test 2026-09-03: `categories[]` och `tags[]` har ingen effekt, `max_nr_of_products` begränsas inte till 100, 1-teckens query ger HTTP 500, ingen stavningstolerans, inga strukturerade specar.

## Att tänka på för vår klient

- `price` är en sträng. Parsa till tal själv om det behövs.
- `get_product` ger inte mer än sökresultatet, snarare mindre (ingen `variations`). Använd sök om varianter behövs.
- Beskrivningar kan innehålla HTML-entiteter.
- Resultatet är på svenska och SE-priser; det finns inga andra språk/länder i schemat i dag.
- Servern är publik och kräver ingen nyckel, men det är en produktionsbutik. Håll anropsvolymen rimlig.

## Ändringar 2026-10-07

Sett när `e37 shop` byggdes. Avsnitten ovan beskriver läget 2026-09-03 och är fel på följande punkter:

- Produkter har `model_number` och `name` i stället för `sku` och `title`. Varianter har `name` i stället för `title`, och storlekar ligger nu bland varianterna bredvid färgerna.
- Kategorier, varumärken och facetter har `name` i stället för `title`. Filtren `categories[]` och `brands[]` beskrivs fortfarande som titlar i schemat.
- `get_product` tar `modelNumber` (föredras, gemensam för alla varianter) eller `gtin` (en variant), inte `sku`. Med `include_specifications: true` kommer `specifications` med, t.ex. färg, material, målgrupp och vikt. Det ger de strukturerade specar som saknades.
- `sort_by` har inte längre `sku_asc`.
- Nya verktyg: `list_pages`, `list_blogs`, `list_blog_posts` (`blog_id`).
- Servern svarar 403 på urllibs standard-User-Agent. Skicka en egen.
