---
name: e37
description: Läs ordrar, rapporter och produkter ur webbshopsplattformen E37 med e37-cli. Använd när användaren frågar om ordrar, orderflöde, försäljning per artikel eller varumärke, moms, återbetalningar, lager, presentkort, en orders status, eller om produkter, priser, lagerstatus och varumärken i en E37-butik (t.ex. Addnature, Outdoorexperten, Cykloteket, Bikester, Rull), vill läsa eller sätta leveranstiden som visas när en vara är slut i lager, eller vill lägga till eller ändra sitt E37-konto. Exempel "vilka ordrar kom in i förmiddags", "vilka varumärken sålde mest på Addnature i veckan", "vad har order 1189437 för status", "har Addnature regnjackor från Patagonia i lager", "lägg till mitt E37-konto".
---

# e37: ordrar, rapporter och produkter ur E37

`e37` är installerat på den här datorn. Kör det som `python -m e37` (`python3 -m e37`
på macOS). Det fungerar även när `e37` inte finns i PATH. Läs `python -m e37 KOMMANDO
--help` när något är oklart. Hjälptexterna är skrivna för dig.

Personen du hjälper är troligen inte tekniskt lagd. Kör kommandona själv och svara
med resultatet i vanlig svenska, inte med kommandoutskrifter.

## Hemligheter: regler som alltid gäller

- Be **aldrig** om API-nyckel, lösenord eller e-post i chatten. Konton läggs in i
  ett fönster på personens skärm med `account add NAMN --dialog`. Du ser aldrig
  uppgifterna.
- Klistrar personen in ett lösenord eller en nyckel: använd det inte. Säg att det
  bör bytas i E37 Admin, och öppna fönstret i stället.
- Skicka aldrig hemligheter via stdin, miljövariabler, filer eller kommandorad.
- Det finns inget kommando som skriver ut en hemlighet. Leta inte efter något.

## Vilket konto?

En person kan ha flera E37-instanser, även för olika bolag. Varje instans är ett
konto med ett kort namn.

```
python -m e37 account list --json
```

ger namn, webbshop-ID, server, om API-nyckel finns (`apiKey`) och e-post för
webbinloggningen (`webEmail`). Finns flera konton måste du ange `--account NAMN`
på `order`, `report` och `sites`. Gissa aldrig, fråga vilken butik eller instans som avses.
Det här är den enda källan till vilka konton som finns.

## Produkter (ingen inloggning)

Butikens publika produktsök. Fungerar utan konto.

```
python -m e37 shop search ORD [ORD ...] --json [--top N] [--in-stock] [--campaign]
                          [--brand NAMN ...] [--sort price_asc|price_desc|latest|...]
                          [--shop addnature|outdoorexperten|URL]
python -m e37 shop product MODELLNUMMER --specs --json
python -m e37 shop brands|categories|tags --json
```

- Sök på 1–2 nyckelord, inte en hel mening. Sökningen behandlar orden som ELLER,
  så "lätt tält för två under 4000" ger regnjackor. Skriv om frågan till "tält 2P"
  och filtrera själv.
- `price` är text (`"3 399 kr"`). Gör om till tal själv för att jämföra eller filtrera på pris.
- Kategori- och taggfilter har ingen effekt hos E37. Filtrera på svaret i stället.
- `model_number` från sökningen används till `shop product`. `--specs` ger färg,
  material, målgrupp och vikt.
- Standardbutik är Addnature. Fråga om butiken om det inte framgår.

## Två vägar in: API-nyckel eller personens egen inloggning

Ett konto kan ha en API-nyckel, en webbinloggning (e-post och lösenord till E37
Admin), eller båda. `account list --json` visar vilket (`apiKey`, `webEmail`).

- **Webbinloggningen** ser allt personen ser i E37 Admin: orderflödet med extra
  kolumner, enskilda ordrar och alla rapporter. De flesta har bara den, och det räcker.
- **API-nyckeln** behövs inte för något. Finns den används den där API:t kan svara.

`e37` väljer själv: API:t när kontot har en nyckel och frågan går att besvara
där, annars webben. Varje körning loggar in på nytt. Ett anrop via webben tar
några sekunder, så slå ihop frågor när det går.

## Webbplatser

En instans har ofta flera webbplatser (butiker per land). Lista dem:

```
python -m e37 sites --account NAMN --json
```

`--site` på `order flow` och `report get` tar id eller namn (`20`, `'Addnature SE'`).
Ett namn som passar flera webbplatser ger fel med alternativen. Fråga då.

## Ordrar

Läser bara. Ändrar ingenting i E37.

```
python -m e37 order flow --account NAMN --json
python -m e37 order flow --account NAMN --from 'ÅÅÅÅ-MM-DD TT:MM' --to 'ÅÅÅÅ-MM-DD TT:MM' [--site 'Addnature SE'] --json
python -m e37 order show ORDERNUMMER --account NAMN --json
python -m e37 order status ORDERNUMMER --account NAMN --json
```

- `order flow` utan tider ger föregående stängda halvtimme, i svensk lokal tid.
  Standard är att ordrar räknas på när betalningen bekräftades (`--mode completed`).
  `--mode created` räknar på när kassan påbörjades, som i E37:s orderöversikt.
- Varje rad har `order_id`, `order_timestamp`, `total_sum_incl_vat`, `total_sum_excl_vat`,
  `currency`, `country`, `site_id`, `site_name`. Via webben dessutom `order_status_title`,
  `payment_method_title`, `shipping_fee_incl_vat`, `erp_import_status` (synk till Garp)
  och `external_marketplace_title`. Summera och gruppera själv.
- `order show` ger kund, adresser, kontaktuppgifter, betalning, leverans, orderrader
  och summering. Det är personuppgifter. Visa bara det som frågan gäller.
  Via webben (utan nyckel) är JSON: `order_id`, `order_timestamp`, `order_status`,
  `site`, `customer_number`, `customer_type`, `payment{method,status,invoice_number}`,
  `delivery{method,pickup_point}`, `other` (t.ex. "Synkad till Garp (Spobik)"),
  `addresses`, `contact`, `rows[{sku,name,quantity,unit_price,sum}]`,
  `summary{"Totalt inkl. moms": …, "Moms": …}`, `notes`. Via API:t är formen E37:s egen.
- `order status` ger orderstatus (Mottagen/ny, Levererad, Annullerad …),
  betalstatus och Garp-synk.

## Rapporter (personens inloggning)

Alla rapporter i E37 Admin, som JSON. Bland annat försäljning per artikel (7)
och per varumärke (21), moms (5), orderhändelser (6), återbetalningar (14),
artikelvarianter med priser och statistik (15), lager per varumärke (4),
presentkort (16–18) och kampanjplanering (23). Id:n kan skilja mellan instanser.
Lita på `report list`.

```
python -m e37 report list --account NAMN --json
python -m e37 report show RAPPORT --account NAMN --json
python -m e37 report get RAPPORT --account NAMN --from 'ÅÅÅÅ-MM-DD TT:MM' --to 'ÅÅÅÅ-MM-DD TT:MM'
                        [--site NAMN] [--set ID=VÄRDE ...] --json
```

- `RAPPORT` är id eller en del av titeln (`varumärken`).
- Kör alltid `report show` först för en rapport du inte använt. Där syns vilka
  inställningar den har, vilka värden som är tillåtna och vad som är standard.
- `--from/--to` fyller rapportens datumintervall i det format den vill ha (vissa
  tar bara datum). Allt annat sätts med `--set ID=VÄRDE`. Kryssrutor är av som
  standard, slå på med `--set ID=true`.
- Svaret är `{"rows": [...], "columns": [...]}`.
- Långa perioder och "alla webbplatser" kan bli stora. Börja med en kort period.

## Leveranstid vid slut i lager (det enda som skriver)

Fältet "Leverans-/beställningstid, om slut i lager" (Lager, Alt. 2, fritext) per
variant. Det syns för kunden när varan är slut. Det finns inte i E37:s exporter.

```
python -m e37 delivery-text get ART [ART ...] --site 'Addnature SE' --account NAMN [--json]
python -m e37 delivery-text get --file lista.xlsx --site 'Addnature SE' --csv nuvarande.csv
python -m e37 delivery-text set --file lista.xlsx --site 'Addnature SE' --text 'Förväntas åter i lager: {date}' --account NAMN
python -m e37 delivery-text set ... --apply --limit 2
python -m e37 delivery-text set ... --apply
```

- Filen är Excel eller CSV med kolumnerna `art-nr` och `datum`. `{date}` i texten
  byts mot radens datum. Olika text per webbplats: `--site-text 'Addnature NO=Forventes tilbake på lager: {date}'`.
- **Texten hör till webbplatsens språk, inte webbplatsen.** Alla svenska webbplatser
  delar samma fält. Sätter du den för Addnature SE ändras den också för OutdoorExperten SE.
  Säg det till personen innan du skriver. Två webbplatser med samma språk och olika
  text nekas.
- **Så här skriver du, i den här ordningen:**
  1. Kör `set` utan `--apply`. Det är en torrkörning som bara läser och visar vad som
     skulle ändras.
  2. Visa personen sammanfattningen: hur många artiklar, vilka webbplatser och språk,
     och exempel på ny text. Fråga om du får spara.
  3. Kör `--apply --limit 2` och visa resultatet.
  4. Kör `--apply` för resten först när personen sagt ja igen.
- Efter varje sparning öppnar verktyget varianten igen. Texten ska vara den nya, och
  inget annat fält får ha ändrats. Står det `ANDRA FÄLT ÄNDRADES` eller `STOPPADE`:
  sluta, kör inget mer och be personen kontrollera varianten i E37 Admin.
- Varje körning skriver en logg (`e37-leveranstid-….csv`) med gammalt och nytt värde.
  Säg var den ligger. Den behövs för att kunna återställa.
- Tömma fältet: `--text ''`.

## Lägga till eller ändra ett konto

```
python -m e37 account add NAMN --dialog
```

Säg först: "Nu öppnas ett litet fönster där du fyller i dina E37-uppgifter. Jag
ser dem inte." Kommandot väntar tills personen tryckt Spara eller Avbryt. Namnet
får bara innehålla a–z, 0–9 och bindestreck, till exempel `vartex-outdoor`.
Samma kommando uppdaterar ett konto. Tomma hemliga fält behåller det som redan
är sparat. Ta bort med `account remove NAMN`.

I fönstret finns:

| Fält | Vad det är |
|---|---|
| Webbshop-ID | Det personen skriver i "Webbshop-ID" när hen loggar in i E37 Admin |
| API-adress | Standard `https://admin3.e37.se/api`; vissa butiker ligger på `admin2` |
| Rapport-konto | Butikens kontonamn i E37:s rapporter, oftast samma som namnet |
| API-nyckel | Valfri. Används där E37:s API kan svara; allt fungerar utan |
| E-post, lösenord | Inloggningen i E37 Admin. Räcker för allt: ordrar, rapporter, webbplatser |

## Fel och vad du gör

| Meddelande | Åtgärd |
|---|---|
| `Inga E37-konton` | Lägg till ett med `account add NAMN --dialog`. |
| `E37 avvisade nyckeln … (401)` | Nyckeln är fel eller indragen. Öppna fönstret för samma namn så kan en ny klistras in. |
| `saknar API-nyckel` | Bara med `--via api`. Ta bort `--via` så används webbinloggningen. |
| `finns inte hos … eller syns inte` | Fel ordernummer, eller fel instans. Prova ett annat `--account`. |
| `saknar webbinloggning` | Öppna fönstret för kontot så att e-post och lösenord kan fyllas i. |
| `Inloggningen i E37 Admin misslyckades` | Fel webbshop-ID, e-post eller lösenord. Öppna fönstret igen. |
| `Flera E37-konton, välj ett med --account` | Fråga vilken instans. |
| `Det går inte att visa en dialog här` | tkinter saknas. Installera om Python från python.org (Windows). |
| `No module named e37` | Inte installerat för den här Python-versionen. Följ https://github.com/Wesports-Scandinavia-AB/e37-cli/blob/main/INSTALL-FOR-CLAUDE.md |

## Uppdatera

När personen ber om det, eller när ett kommando i den här texten inte finns:

```
python -m e37 update
```

Det hämtar senaste versionen från GitHub och skriver om den här instruktionen.
Kontona ligger kvar. Läs om instruktionen efteråt med `python -m e37 skill show`.
Versionen visas med `python -m e37 --version`.

Avinstallera med `python -m pip uninstall e37-cli`. Ta först bort kontona med
`account remove`, annars ligger de kvar i nyckelringen.
