# Instruktion till Claude: installera e37-cli

Den här filen är skriven till dig, Claude, inte till människan du hjälper. Någon
har gett dig länken för att få `e37-cli` installerat. Det är ett verktyg som läser
ordrar och produkter ur webbshopsplattformen E37.

Följ stegen i ordning. Kör kommandona själv och förklara kort på vanlig svenska.
Personen är troligen inte tekniskt lagd och ska inte behöva skriva några kommandon.

## 0. Kan du köra kommandon?

Du måste kunna köra kommandon på personens dator, till exempel i Claude Code eller
fliken **Code** i Claude-appen. Kan du inte det, som i en vanlig chatt, säg det
rakt ut. Be personen öppna Claude-appen, välja **Code** och ge dig länken igen.
Stanna där.

**Be aldrig om lösenord, API-nyckel eller e-post i chatten**, inte heller under
installationen. Det finns ett eget fönster för det i steg 4.

## 1. Python

```
python --version      # Windows
python3 --version     # macOS
```

Det krävs 3.9 eller senare. Saknas Python:

- **Windows:** `winget install --id Python.Python.3.12 -e`. Starta sedan en ny
  terminalsession så att `python` hittas.
- **macOS:** `xcode-select --install`. Det ger `python3`.

I resten av texten står `python`. På macOS skriver du `python3`.

## 2. Installera e37-cli

```
python -m pip install --user --upgrade git+https://github.com/Wesports-Scandinavia-AB/e37-cli
```

Saknas git, eller klagar pip på git, byt adressen mot
`e37-cli @ https://github.com/Wesports-Scandinavia-AB/e37-cli/archive/refs/heads/main.zip`.
Kör du i en virtuell miljö, ta bort `--user`.

Kontrollera:

```
python -m e37 --version
```

Använd alltid `python -m e37`. Då fungerar det oavsett om `e37` hamnat i PATH.

## 3. Installera skillen

```
python -m e37 skill install
```

Det lägger `SKILL.md` i `~/.claude/skills/e37/`. Den laddas automatiskt i
kommande samtal, så att Claude vet hur `e37` används även nästa gång. Läs den nu:

```
python -m e37 skill show
```

**Från och med här gäller skillen.** Den beskriver kommandona, reglerna för
hemligheter, hur rätt konto väljs och vad felmeddelandena betyder.

## 4. Lägg till personens E37-konto

Gör som skillen säger under "Lägga till eller ändra ett konto". Kort: fråga vad
instansen ska heta, säg att ett fönster öppnas där personen själv fyller i sina
uppgifter, och kör:

```
python -m e37 account add NAMN --dialog
```

Kontrollera sedan med `python -m e37 account list`.

## 5. Klart

Berätta vad personen kan fråga om nu, till exempel "vilka ordrar kom in i
förmiddags?" eller "har Addnature regnjackor i lager?". Säg också att det räcker
att säga "uppdatera e37" när det kommit en ny version.
