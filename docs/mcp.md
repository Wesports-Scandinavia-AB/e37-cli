# E37:s MCP-server

E37 är webbshopsplattformen bakom bland annat addnature.com och outdoorexperten.se (sessionscookien heter `e37webshopSession`, bilder ligger på `cdn37.se`). Varje butik exponerar en egen MCP-server på samma sökväg.

Undersökt 2026-09-03.

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
| `variations` | array | Finns i sökresultat. Form ej dokumenterad ännu. |

### list_categories

`[{"id":4780,"title":"Kläder","url":"...","image_url":"..."}]` (`image_url` saknas ibland).

### list_brands

`[{"id":305,"title":"2117 of Sweden","url":"...","nr_of_products":77}]`

## Att tänka på för vår klient

- `price` är en sträng. Parsa till tal själv om det behövs.
- Beskrivningar kan innehålla HTML-entiteter.
- Resultatet är på svenska och SE-priser; det finns inga andra språk/länder i schemat i dag.
- Servern är publik och kräver ingen nyckel, men det är en produktionsbutik. Håll anropsvolymen rimlig.
