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
