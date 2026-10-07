# E37:s webbgränssnitt

Anteckningar inför en modul i `src/e37/` som gör det i E37 Admin som API:et inte kan. Den finns inte än.

## Vad vi vet om webben

E37:s webb är byggd på ASP.NET WebForms, inte JSON-endpoints. Det innebär:

- Sidor är server-renderad HTML med ett stort `<form>` per sida.
- Varje åtkomst är en POST-back med `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`, `__EVENTTARGET` och `__EVENTARGUMENT`.
- Man måste alltid först GET:a sidan, plocka ut de dolda fälten, och skicka dem tillbaka i POST:en. Fälten är sidspecifika och ändras mellan requests.
- Fält heter ofta `ctl00$MainContent$...`. Ta namnen från HTML:en i stället för att hårdkoda dem där det går.
- Inloggning är en form-POST som ger en sessionscookie (`ASP.NET_SessionId` och/eller `.ASPXAUTH`). Cookien måste följa med i alla anrop.

## Rekommenderad ansats

Byggs med [Scrapling](https://github.com/D4Vinci/Scrapling), installerat som `pip install e37-cli[web]`. Beslut 2026-10-07: resten av paketet klarar sig på standardbiblioteket, men här behövs cookies, HTML-parsning och kanske en riktig webbläsare.

1. **Först: Scraplings `Fetcher` med session.** Hämta sidan, plocka ut de dolda fälten med selektorer, bygg POST-body med ViewState-fälten och `__EVENTTARGET` för den kontroll som ska "klickas", skicka som `application/x-www-form-urlencoded`.
2. **Bara om det inte räcker: `DynamicFetcher`/`StealthyFetcher`**, alltså en riktig webbläsare. Behövs om sidan använder UpdatePanel/AJAX-postbacks med tung klientlogik.

## Regler

- Använd bara för det som saknas i `admin.py`.
- Dokumentera varje funktion med vilken lucka i API:et den täcker, så att den kan tas bort när API:et hinner ikapp.
- Hantera att ViewState blir ogiltig (session löpt ut, sida ändrad). Logga in igen och hämta om sidan i stället för att krascha.
- Spara aldrig sessioncookies i repot.

Fylls på när det är klart vilka luckor som behöver täckas.
