# Test: chatta om produkter via E37:s MCP (Addnature)

Utfört 2026-09-03 mot `https://www.addnature.com/api/mcp`. Jag spelade LLM:en och körde ett realistiskt kundflöde: "Jag ska fjällvandra i september och behöver ett lätt tvåmannatält, budget 4 000 kr." Därefter systematiska tester av varje filter och parameter.

## Slutsats

Servern fungerar tekniskt och räcker för "hitta produkter som matchar ett sökord, visa pris och lagerstatus". Den räcker inte för rådgivande produktchatt utan att LLM:en gör mycket eget jobb, eftersom sökningen är ren fritextsökning utan produkttypsfacett, kategori- och taggfiltren inte har någon effekt, och specifikationer som vikt bara finns som fritext i beskrivningen.

## Vad som fungerar

| Funktion | Resultat |
|---|---|
| Fritextsök på svenska | Ja. `tält` gav 161 träffar, `tält 2P` 186. |
| Fritextsök på engelska | Ja, men färre träffar. `tent` gav 40. Titlar är ofta på engelska så det hjälper. |
| `brands[]`-filter | **Fungerar.** `brands=['Bergans']` gav 9 av 161. |
| `in_stock_only` | Fungerar. 161 → 120. |
| `campaign_only` | Fungerar. 161 → 24. |
| `sort_by` | Fungerar. `price_asc` och `latest` ger olika ordning. |
| `max_nr_of_products` | Fungerar, men gränsen på 100 i schemat upprätthålls inte. 150 gav 150 rader. |
| Facetter i svaret | `categories`, `brands`, `tags` med antal per värde följer med. Kategorifacetterna uppdateras korrekt när man filtrerar på brand, men brand-facetterna uppdateras inte. |
| `variations` | Färg/storlek med lagerstatus per variant. Bra för "finns den i grönt?". |
| `get_product` | Fungerar, men ger ingen extra information jämfört med sök. Saknar `variations`. |

## Vad som inte fungerar eller saknas

| Problem | Detalj |
|---|---|
| **`categories[]` har ingen effekt** | `categories=['Skor']` på `tält` borde ge 1 träff enligt facetten, gav 161. Testat med titel (`Vandring`, `Skor`) och id (`4124`). Ingen skillnad. |
| **`tags[]` har ingen effekt** | Testat med exakt nyckel från facetterna (`#activity camping`, `#gender dam`). 161 träffar oavsett. |
| `price_range` | Markerad "not implemented" i schemat. Inte testad. |
| Ingen produkttypsfacett | Det finns bara 11 toppkategorier (Kläder, Skor, Utrustning, Vandring …). Ingen "Tält"-nivå. En sökning på `tält` blandar tält med tältpinnar, lampor, drybags och repslut. Sortering på pris ger därför tillbehör först. |
| Ingen stavningstolerans | `tellt` gav 0 träffar. |
| Naturligt språk fungerar dåligt | `lätt tält för två under 4000 kr` gav 863 träffar med regnjackor först. Söket verkar OR:a orden. LLM:en måste destillera frågan till 1–2 nyckelord. |
| Ingen strukturerad spec | Vikt, antal personer, packmått etc. finns bara i `description` som fritext, och ibland saknas beskrivning helt (Bergans Romsdal 2 hade ingen). Går inte att filtrera eller sortera på. |
| `price` är text | `"5 289 kr"`. Kan inte jämföras utan parsning. |
| Märken som inte finns | `Hilleberg` gav 0 träffar, vilket är korrekt, men servern säger inte "märket finns inte" utan bara 0. |
| Kort query | 1 tecken ger HTTP 500 i stället för ett JSON-RPC-fel. |
| `serverInfo` | Ger `protocolVersion 2024-11-05` oavsett vad klienten begär. |

## Exempel ur flödet

Sökning `tvåmannatält` gav 4 träffar, varav ett enmanstält och två slutsålda. Breddning till `tält 2P` fungerade bäst av allt jag provade och gav Marmot Superalloy 2P (5 289 kr, 1 020 g enligt beskrivningen), Marmot Trailfin 2P, m.fl. För att svara på "under 4 000 kr" måste LLM:en hämta upp till 100 träffar, parsa prissträngen och filtrera själv.

## Rekommendation för vår MCP i `mcp/`

Om vi bygger en egen MCP-server ovanpå E37 bör den kompensera för ovanstående:

1. **Egen produkttypsklassning** eller använda E37:s underkategorier via webben/API om de finns. Det är den enskilt största bristen.
2. **Parsa `price` till tal** och exponera `price_min`/`price_max`-filter på vår sida.
3. **Extrahera nyckelspecar ur `description`** (vikt, antal personer, packmått) med regex eller LLM, cachea per SKU.
4. **Normalisera queries** innan de skickas vidare: plocka ut 1–2 substantiv, ta bort prisuttryck och fyllnadsord.
5. **Implementera kategori- och taggfilter själva** genom att hämta upp till 100 träffar och filtrera på facetterna i svaret, eftersom E37:s filter inte fungerar.

## Att ta upp med E37

- `categories[]` och `tags[]` i `search_products` har ingen effekt. Bugg eller odokumenterat format?
- Kan `price_range` implementeras?
- Kan produkter få strukturerade attribut (vikt, personer, storlek) i svaret?
- Finns underkategorier att söka på?
- 1-teckens query ger HTTP 500.

## Svarsstorlek och svarstid

Mätt 2026-09-03. Varje produkt kommer med hela beskrivningen, så storleken växer snabbt.

| Anrop | Storlek | Ungefär tokens | Svarstid |
|---|---|---|---|
| `search_products`, 5 produkter | 10 KB | 2 700 | 250 ms |
| `search_products`, 30 produkter (default) | 46 KB | 11 700 | 310 ms |
| `search_products`, 100 produkter | 155 KB | 39 700 | 570 ms |
| `get_product` | 2 KB | 450 | 230 ms |
| `list_brands` (303 märken) | 35 KB | 9 000 | 120 ms |
| `list_tags` (157 taggar) | 11 KB | 2 800 | 90 ms |

Svarstiderna är inget problem. Tokenkostnaden är det: några sökningar med default-antalet fyller kontexten i ett chattsamtal. Sätt `max_nr_of_products` till 5–10 i en chatt.

## Bedömning: E37:s MCP direkt i Zendesk-chatten på siten

Frågan ställdes 2026-09-03. Slutsats: koppla inte in den direkt.

**Hade fungerat**

- Uppslag på namngiven produkt: lager, pris, kampanj, färgvarianter. Bra värde utanför öppettider.
- "Vad är på rea bland X?" via `campaign_only`.

**Hade gått dåligt**

- Supportfrågor, som är merparten av chatttrafiken. "Var är min order" gav 171 produkter, "returnera" gav 18. MCP:n har inget om order, leverans eller retur. Order-API:t behövs för det.
- Stavfel ger noll träffar, och agenten skulle svara "vi har inga tält". Falska "finns inte"-svar är värre än inget svar.
- Rådgivning ("vilket tält till fjällen i september?") kräver att modellen sållar tillbehör, parsar vikt ur fritext och gissar när beskrivning saknas. Hög risk för självsäkra felaktiga rekommendationer.
- Om modellen skickar kundens hela mening som sökord blir resultatet skräp (regnjackor på en tältfråga).
- Tokenkostnad per anrop, se tabellen ovan.

**Rekommendation**

Lägg vår egen MCP i `mcp/` mellan Zendesk och E37. Den ska hålla `max_nr_of_products` lågt, normalisera sökord till 1–2 nyckelord, söka igen på engelska vid noll träffar, filtrera bort tillbehör, parsa pris till tal, och exponera orderuppslag från Order-API:t så snart nyckeln finns. Kontrollera också om Zendesks AI-agent kan konsumera en extern MCP-server; annars behöver vår server även ett vanligt HTTP-API.
