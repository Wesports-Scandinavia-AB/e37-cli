---
name: e37
description: Läs ordrar och produkter ur webbshopsplattformen E37 med e37-cli. Använd när användaren frågar om ordrar, orderflöde, en orders status, eller om produkter, priser, lagerstatus och varumärken i en E37-butik (t.ex. Addnature, Outdoorexperten, Cykloteket, Bikester, Rull), eller vill lägga till eller ändra sitt E37-konto. Exempel "vilka ordrar kom in i förmiddags", "vad har order 1189437 för status", "har Addnature regnjackor från Patagonia i lager", "lägg till mitt E37-konto".
---

# e37: ordrar och produkter ur E37

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
på orderkommandona. Gissa aldrig, fråga vilken butik eller instans som avses.
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

## Ordrar (kräver konto med API-nyckel)

Läser bara. Ändrar ingenting i E37.

```
python -m e37 order flow --account NAMN --json
python -m e37 order flow --account NAMN --from 'ÅÅÅÅ-MM-DD TT:MM' --to 'ÅÅÅÅ-MM-DD TT:MM' --json
python -m e37 order show ORDERNUMMER --account NAMN --json
python -m e37 order status ORDERNUMMER --account NAMN --json
```

- `order flow` utan tider ger föregående stängda halvtimme. Med tider räknas
  svensk lokal tid. Ordrar räknas på när betalningen bekräftades, inte när de skapades.
- Varje rad i `order flow` har `order_id`, `order_timestamp`, `total_sum_incl_vat`,
  `total_sum_excl_vat`, `currency`, `country`, `site_name`. Summera och gruppera själv.
- `order show` ger kund, adresser, betalning, leverans och orderrader. Det är
  personuppgifter. Visa bara det som frågan gäller.
- Orderdelen är byggd efter E37:s dokumentation och har ännu inte körts mot en
  riktig nyckel. Ser svaret annorlunda ut än beskrivet, säg det och visa vad du fick.

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
| API-nyckel | Skapas i E37 Admin. Behövs för orderkommandona |
| E-post, lösenord | Inloggningen i E37 Admin. Används inte av något kommando än |

## Fel och vad du gör

| Meddelande | Åtgärd |
|---|---|
| `Inga E37-konton` | Lägg till ett med `account add NAMN --dialog`. |
| `E37 avvisade nyckeln … (401)` | Nyckeln är fel eller indragen. Öppna fönstret för samma namn så kan en ny klistras in. |
| `saknar API-nyckel` | Samma åtgärd. |
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
