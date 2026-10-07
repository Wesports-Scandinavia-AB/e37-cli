# Instruktion till Claude: installera och använd e37-cli

Den här filen är skriven till dig, Claude, inte till människan du hjälper. Du har
fått länken för att installera `e37-cli` åt någon och sedan använda det åt dem.

`e37-cli` hämtar ordrar och produkter ur webbshopsplattformen E37: orderflöde,
enskilda ordrar och status via E37 Admin, och produktsök via butikens publika
MCP-server.

## Vem du hjälper

Personen är troligen inte tekniskt lagd och har inte använt en terminal. Kör
alla kommandon själv, förklara på vanlig svenska vad du gör, och be dem inte att
skriva kommandon.

## Krav

Du måste kunna köra kommandon på personens dator, till exempel i Claude Code
eller fliken Code i Claude-appen. Kan du inte köra kommandon, som i en vanlig
chatt på claude.ai, ska du säga det rakt ut. Be personen öppna Claude-appen,
välja Code och ge dig länken igen. Försök inte på något annat sätt.

## Regler för hemligheter (viktigast)

- **Be aldrig om API-nyckel, lösenord eller e-post i chatten.** Uppgifterna matas
  in i ett fönster som `e37` öppnar på personens skärm. Du ser dem aldrig.
- Klistrar personen ändå in ett lösenord eller en nyckel i chatten: använd det
  inte. Säg att det bör bytas i E37 Admin, och öppna fönstret i stället.
- Skicka aldrig JSON med hemligheter till `e37 account add` via stdin, och lägg
  dem aldrig i miljövariabler, filer eller kommandorader.
- `e37 account list` visar vilka hemligheter som finns, aldrig värdena. Det finns
  inget kommando som skriver ut dem, och du ska inte leta efter något sätt.

## 1. Installera

Ta reda på operativsystem och Python-version:

```
python --version      # Windows
python3 --version     # macOS
```

Det behövs Python 3.9 eller senare. Saknas Python:

- **Windows:** `winget install --id Python.Python.3.12 -e`. Öppna sedan en ny
  terminalsession så att `python` hittas.
- **macOS:** `xcode-select --install` ger `python3`. Den inbyggda `python3` räcker.

Installera paketet för den inloggade användaren:

```
python -m pip install --user --upgrade git+https://github.com/Wesports-Scandinavia-AB/e37-cli
```

På macOS heter det `python3`. Kör sedan programmet som `python -m e37` (eller
`python3 -m e37`). Då fungerar det oavsett om `e37` hamnat i PATH. Kontrollera:

```
python -m e37 --help
```

Finns inte git på datorn, byt adressen mot
`https://github.com/Wesports-Scandinavia-AB/e37-cli/archive/refs/heads/main.zip`.

## 2. Lägg till ett E37-konto

Varje E37-instans som personen loggar in i blir ett konto med ett kort namn,
till exempel `vartex-outdoor`. Namnet får bara innehålla a–z, 0–9 och
bindestreck. Fråga vad instansen ska heta, eller föreslå ett namn utifrån
butiken. Säg sedan ungefär: "Nu öppnas ett litet fönster där du fyller i dina
E37-uppgifter. Jag ser dem inte." Kör:

```
python -m e37 account add NAMN --dialog
```

Kommandot väntar tills personen tryckt Spara eller Avbryt. Fönstret frågar efter:

| Fält | Var personen hittar det |
|---|---|
| Webbshop-ID | Det de skriver i fältet "Webbshop-ID" när de loggar in i E37 Admin |
| API-adress | Låt standardvärdet stå om de inte vet bättre (`https://admin3.e37.se/api`; vissa butiker ligger på `admin2`) |
| Rapport-konto | Butikens kontonamn i E37:s rapporter. Oftast samma som namnet |
| API-nyckel | Skapas i E37 Admin. Får lämnas tomt; då fungerar inte orderkommandona |
| E-post och lösenord | Deras inloggning i E37 Admin. Får lämnas tomt tills vidare |

Kontrollera efteråt med `python -m e37 account list`. Fler instanser läggs till
på samma sätt, med ett nytt namn var. Ett konto uppdateras med samma kommando
och tas bort med `python -m e37 account remove NAMN`.

Uppgifterna hamnar i datorns egen nyckelring: Credential Manager på Windows,
Nyckelringar på macOS. Inget sparas i filer.

## 3. Använd

Lägg till `--json` när du själv ska läsa svaret. Utan `--json` blir det en
sammanfattning som är lätt att visa för personen.

```
python -m e37 shop search regnjacka --top 5 --in-stock      produkter (ingen inloggning behövs)
python -m e37 shop product 152668-0073 --specs               en produkt med specifikationer
python -m e37 shop search jacka --shop outdoorexperten       annan butik
python -m e37 order flow --account NAMN                      ordrar senaste stängda halvtimmen
python -m e37 order flow --account NAMN --from '2026-10-07 08:00' --to '2026-10-07 12:00'
python -m e37 order show 1189437 --account NAMN              en order i detalj
python -m e37 order status 1189437 --account NAMN            en orders status
```

Med fler än ett konto måste du alltid ange `--account`. Gissa aldrig vilken
instans personen menar, fråga hellre.

Allt ovan läser och ändrar ingenting i E37. Det finns inga kommandon som skriver
till E37 än.

## Felsökning

| Meddelande | Gör så här |
|---|---|
| `E37 avvisade nyckeln … (401)` | Nyckeln är fel eller har dragits tillbaka. Öppna fönstret igen med samma namn, så kan personen klistra in en ny. |
| `saknar API-nyckel` | Kontot har ingen nyckel. Samma åtgärd. |
| `Det går inte att visa en dialog här` | Python saknar tkinter. På Windows: installera om Python från python.org eller winget. På macOS används en reserv automatiskt. |
| `Flera E37-konton, välj ett med --account` | Fråga personen vilken instans som avses. |

## Uppdatera

Kör installationskommandot igen. `--upgrade` hämtar senaste versionen.
