# E37:s webbgränssnitt

Karta över E37 Admin (`https://admin3.e37.se/`) som webbgränssnitt, och hur `src/e37/web.py` läser det med personens egen inloggning.

Selektorer och flöden är kartlagda 2026-10-06 med Playwright mot en riktig instans med fyra webbplatser. Ingenting här är verifierat med `e37-cli` än. Markera det som **[verifierat ÅÅÅÅ-MM-DD]** när vi själva har sett det.

## Verifierat 2026-10-07 (det `src/e37/web.py` bygger på)

Kört med `urllib` och en cookie-jar, utan webbläsare, mot en riktig instans med 21 webbplatser.

| Vad | Hur |
|---|---|
| Inloggning | GET `/` skickar till `login.aspx?ReturnUrl=%2f`. POST samma adress med de dolda `__VIEWSTATE`-fälten, `tbAccountName` (webbshop-ID), `tbEmail`, `tbPassword` och `btnLogin.x`/`btnLogin.y` (bildknapp). Lyckad om svaret innehåller `ddlSitePicker`. Cookies: `.E37ADMINSESSION`, `.E37ADMINAUTH`, `TritonAdminLogin`. |
| Webbplatser | Options i `ctl00$ddlSitePicker` på startsidan. Standardbutiken har `(standard)` i namnet. |
| Rapporttyper | Options i `ctl00$cph1$ddlReportType` på `workspace/workwith/reports.aspx`. 28 typer. |
| Rapportens inställningar | Postback med `__EVENTTARGET=ctl00$cph1$ddlReportType` och vald typ. Inställningarna ritas som `<div data-setting-id=… data-setting-type=…>` med input, select, radio eller checkbox i. |
| Ladda ner en rapport | GET `/custom/orderReportHandler.ashx?data=…&reportType=ID&fileType=5`. `data` är `id:värde` per inställning, åtskilda med `¤`. Kryssrutor `true`/`false`, datumintervall `från,till` i rapportens format. `fileType` 5 är JSON (1 tabb, 2 semikolon, 3 Excel). Svaret är `{"rows": […], "columns": […]}` med `Content-Disposition: attachment`. |
| Ordersidan | `workspace/workwith/orders.aspx` listar ordrar från alla webbplatser i `#ctl00_cph1_tblOrders`. Filter för datum, betalstatus, orderstatus, kundnummer och fritext. Kryssrutorna heter `checkbox|ORDERID|SITEID|1`. |
| En order | `ViewOrder(id)` är en postback `__EVENTTARGET=__Page`, `__EVENTARGUMENT=viewOrder?ID` mot `orders.aspx`. En vanlig synkron postback räcker, och orderrutan ritas i sidan. Fliken Allmänt (`…PopupTab1`) har allt: `div.piece` med `bigtext` (Datum & tid som "Idag 22:53", Ordernummer, Kundnummer, Garp-synk), etikett/värde-tabeller (Webbplats, Kundtyp, Momsland, Orderbekräftelse, betalningens Status och Fakturanr), `div.addressItem` med `label.cart` (Fakturaadress, Leveransadress, E-post, Telefon), `tr.cartRow` i `cartTable` (Artnr, Artikel, –, Antal, À pris, Summa), `table.orderSummary`, `roundedBoxPayment`/`roundedBoxDelivery` med metoden i `span.subtitle`, och `ddlOrderStatus`. Fel ordernummer ger ingen ruta. Rutan har knappar som ändrar ordern; de postas aldrig. |
| Artikelregistret | `workspace/workwith/articles/list.aspx`. Sök: fältet `…tabSearch$txtSearch` och bildknappen `…tabSearch$btnArticleSearch` (inte `btnSearch`). Varianterna finns redan i HTML:en som `tr.av` med `data-article-variant-id` och `data-article-variant-nr`. Utfällningen sker bara i webbläsaren. |
| En variant | `EditAv('id=N;')` är `pagePostbackAsync("a", …)`, alltså `__EVENTTARGET=__Page`, `__EVENTARGUMENT=a_id=N;`. En synkron postback räcker. Fältet: `…PopupTab3$LanguageTabContainer2$tbDeliveryTimeText$<språk>` (inte `…InStock…`, inte `$hidden<språk>`). Spara: hela formuläret, `…PopupTab3$changesMadeHiddenField=1` och bildknappen `ctl00$cph1$mod1$pnl$usrCtrl$btnSave`. **Texten är per språk:** alla svenska webbplatser visar samma fält (verifierat 2026-10-08). |
| Byta webbplats | Postback med `__EVENTTARGET=ctl00$ddlSitePicker` och nytt värde. Det är sessionstillstånd. |
| Andra handlers | `/custom/print.ashx?printType=1|2|3&orderid=` (följesedel, kvitto, returnota), `/custom/exportListHandler.ashx`, `/custom/exporthandler.ashx`. Inte undersökta. |

## Marknadsregistren (verifierat 2026-10-09, läser bara)

`src/e37/registers.py`, kommandot `e37 view`. Underlaget är det marknad arbetar med: kampanjer, rabattkoder, badger, kampanjsidor, topprodukter, tillval som är slut och storlekssortering. Allt nedan är läsning. Inget av det skriver.

| Sort (`e37 view …`) | Sida | Listan | Öppna en post (`__EVENTTARGET=__Page`) |
|---|---|---|---|
| `campaigns` | `workspace/workwith/prices/campaigns.aspx` | `table#tblCampaigns`, `tr.listRow` | `openListItem('open', N)` → `open|N` |
| `discount-codes` | `workspace/workwith/prices/discountcodes.aspx` | tabeller per flik (Rabattkoder, Engångskoder) | `EditDiscountCode('id=N;')` → `open|id=N;` (engångskoder har `type=2` i strängen) |
| `tags` | `workspace/workwith/articles/tags.aspx` | träd, `div.node[data-item-id]`, barn i `div.childNodes` | `EditArticleTag` → `open_id=N;site=S;` |
| `attributes` | `workspace/workwith/articles/attribute_list.aspx` | en tabell per kategori under `<h3>` | `EditAttributeType` → `edit_id=N;` |
| `pages` | `workspace/layout/pages/contentpages.aspx` | träd, flikar Sidor och Systemsidor | `EditContentPage` → `1|…`, `EditShopPage` → `2|…` |
| `content` | `workspace/layout/contentElements.aspx` | tabell | `ShowCategory` → `open_id=N;` |
| `widgets` | `workspace/layout/widgets/widgets.aspx` | tabell per flik | `EditWidgetContainer` → `edit_id=N;` |
| `addition-sets` | `workspace/workwith/articles/AdditionSets.aspx` | tabell, med `tr.sub` som räknar upp tillvalsartiklarna | `EditAdditionSets` → `edit_id=N;` |
| `matrices` | `workspace/workwith/articles/matrix_list.aspx` | tabell | `EditMatrixType` → `open_id=N;` |

- **Samma postback tar bort.** Funktionerna som öppnar en post (i `/bundles/scripts`) skickar `doPostBackAsync('__Page', prefix + qs)`. Syskonfunktionerna skickar `del|`, `del_`, `delete|`, `delbatch|` och `copy|` på samma sätt. Därför bygger `registers.py` aldrig argumentet själv. Det tas från postens egen länk på listsidan, och bara för funktionerna i `_OPENERS`. Rör aldrig bildknapparna `delete<N>`/`button<N>` i listorna, eller något i dialogerna.
- En vanlig synkron postback räcker, precis som för variantdialogen. Dialogen ritas som `div.modalpopup`. Rubriken står i `div.topContent`, flikarna i `li[id$="popupTabItem|PopupTabN"]` och innehållet i `div#…_PopupTabN.popupTabContent`.
- **Etiketter** finns i tre former: `span.triton-label > label` (tillval, taggar, matriser), en lös `<label>` före fältet (kampanjer, rabattkoder) och en cell före fältet på samma tabellrad (innehållselement, där kolumnen Beskrivning är etiketten).
- **Underlistor:** tillvalsartiklarna är `div.dragAndDropItem` i ordning, och ikonens `title` innehåller E37:s varning när en artikel inte går att köpa ("Tillvalsartikeln har inte någon publicerad artikelvariant", "Ingen artikelvariant är köpbar i webbplats …", med senaste köpbara datum). En taggs artiklar är tabellrader med en kryssruta `cbDelete_N`.
- Listikonernas `title` ger status: "Pågår", "Avslutad" med slutdatum, "(Inaktiv)", "Aktiverad", "Dold", "Tidsstyrd version: …".
- Sidorna är stora: kampanjlistan är ca 0,6 MB och en öppnad kampanj ca 7 MB, eftersom alla varugrupper och varumärken ligger som options. Att öppna en post tar några sekunder.
- Taggar och sidor gäller den valda webbplatsen (`site=` i argumentet). `--site` byter först.

### Spara en post (`e37 change`, verifierat 2026-10-09)

Provat på en tagg utan artiklar och en inaktiv kampanj: satt, kontrollerat och återställt.

- Hela formuläret serialiseras som en webbläsare gör (`_form_full`), bara de ändrade fälten byts, `…$PopupTabN$changesMadeHiddenField=1` sätts för fliken där fältet står, och bildknappen `…$pnl$usrCtrl$btnSave` skickas med `.x`/`.y`. En vanlig synkron postback räcker.
- **`…$usrCtrl$isPostback` måste vara `1`.** Sidans eget skript sätter det när dialogen laddas. Står det kvar på `0` laddar servern om posten från databasen innan den sparar, och ändringen försvinner utan felmeddelande. Dialogen stängs ändå, så en stängd dialog bevisar ingenting.
- Fält med rik text (TinyMCE, namn som slutar på `$sv` osv.) har ett syskon `…$isDirty` som webbläsaren sätter till språkkoden. Det sätts likadant.
- Språkfälten (`languageTextBox`, flaggor ovanför) gäller det språk som visas, och det följer webbplatsen. Att byta språk i dialogen är en egen postback (`…LanguageTabContainerN`, argument språkkoden). `e37 change` byter i stället webbplats med `--site`.
- Låsta fält (`disabled`), till exempel valutan på en rabattkod, nekas med ett eget fel.
- Efter sparning öppnas posten igen och alla fält jämförs. Det är enda beviset.

### Tillval i en tillvalsuppsättning (`e37 additions`, verifierat 2026-10-09)

Provat på uppsättningen "Vikbart lås", som ingen artikel använde: lagt till, tagit bort, bytt och bytt tillbaka.

- Varje tillval i listan har en länk `EditAdditionalArticle("articleMainId=SET;additionalArticleMainId=ART;additionNr=N;additionPurchaseMode=1")`. Det är `doPostBackAsync('…$pnl$usrCtrl', argument)` och öppnar en inbäddad dialog, `…$usrCtrl$imp$pnl$usrCtrl`, med tillvalets inställningar.
- **Artikeln väljs med ett sökfält.** GET `/service/autoCompleteArticlesExcludePackages?query=…` ger `{"suggestions": [{"value", "data": "huvudid|namn|artnr"}]}`. Valet postas som `__EVENTTARGET=…$imp$pnl$usrCtrl$PopupTab1$autoArticle`, `__EVENTARGUMENT=<data>`, och dialogen ritas om med artikelns varianter.
- **Den inbäddade dialogens Spara sparar direkt** (`…$imp$pnl$usrCtrl$btnSave`), utan ytterdialogens Spara. Ett nytt tillval (`…$PopupTab2$btnAdd`) eller en bytt artikel finns i E37 så fort den sparats.
- **Ta bort väntar däremot på ytterdialogen.** `…$PopupTab2$deleteButton_N` tar bort ur listan i dialogen, men först ytterdialogens Spara (med `PopupTab2$changesMadeHiddenField=1`) tar bort det i E37. `N` hör till listraden, inte till artikeln; läs den ur raden.
- Att byta artikel på ett befintligt tillval behåller plats och inställningar. Begränsade eller förvalda varianter hör till den gamla artikeln, så det bytet nekas.

### Taggar på artiklar (`e37 tag`, verifierat 2026-10-09)

Provat med taggen "Lagerrensning" (ingen egen sida, inga artiklar) på en artikel i produktkyrkogården: lagt till, kontrollerat i taggen, tagit bort.

- Taggdialogen kan bara ta bort artiklar (kryssruta `cbDelete_N`, sedan Spara). Taggar sätts från artikelregistret.
- **Massuppdatering:** `pagePostbackAsync("massupdate", "[huvudid,…]")` på `articles/list.aspx`, alltså `__EVENTTARGET=__Page`, `__EVENTARGUMENT=massupdate_[78456,…]`. Artiklarna behöver inte vara sökta först. Dialogen heter "Massuppdatera artiklar" och ligger under `ctl00$cph1$mod1$pnl$usrCtrl`.
- Varje fält har en egen kryssruta (`cbUpdateTags`, `cbCampaignText`, `cbUpdateAddSets` …) som säger att just det ska uppdateras. Allt annat lämnas orört.
- Taggar: `cbUpdateTags=on`, radio `tagEdit` (Lägg till tagg / Ta bort tagg), och AutoSuggest-fälten `…$articleTags$AutoSuggestHidden` = `id;namn;` och `…AutoSuggestHidden2` = JSON-listan som webbläsaren håller. Förslagen kommer från GET `/service/autoSuggestTagsExcludeGeneratedByAttribute?term=…` (`[{value, label, concat}]`). Taggar som genereras från attribut går inte att välja.
- Massuppdateringen har också Undertitel och Etikett (per språk), varumärke, tillvalsuppsättningar (lägg till eller ersätt), leveranstider, lagerprofil, artikelkategori med mera.
- Bevis: taggens egen artikellista läses före och efter.

**Kommer inte med än:**

- Värdelistan för ett attribut, till exempel värdena i `#CAMPAIGN`. Fliken laddas troligen för sig.
- Matrisvärdena och deras ordning (storlekssorteringen).
- Innehållet på en sida och i en widgethållare (widgetar, texter och bilder per språk). Dialogen visar bara sidans inställningar och layout.
- Texter för andra språk än webbplatsens. Språkflikarna (`LanguageTabContainer`) visar ett språk åt gången.

Kartan nedan, med artikelregistret och variantdialogen, är från en tidigare kartläggning med Playwright och inte verifierad med `web.py`.

## Grunder

E37 Admin är ASP.NET WebForms, inte JSON-endpoints:

- Sidor är server-renderad HTML med ett stort `<form>` per sida.
- Varje åtgärd är en POST-back med `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`, `__EVENTTARGET` och `__EVENTARGUMENT`. Sidan måste GET:as först och de dolda fälten skickas tillbaka. De är sidspecifika och ändras mellan requests.
- Kontroller heter `ctl00$cph1$...` i `name` och `ctl00_cph1_...` i `id`. `cph1` är sidans innehållsplatshållare.
- Sessionen är en cookie (`ASP.NET_SessionId` och/eller `.ASPXAUTH`) som måste följa med i alla anrop.
- Sökning och butiksbyte är fullständiga postbacks. Sidan laddas om.

## Inloggning

| | |
|---|---|
| Sida | `login.aspx`. `https://admin3.e37.se/` skickar dit om man inte är inloggad. |
| Fält | Etiketterna **Webbshop-ID**, **Epost**, **Lösenord** |
| Knapp | **Logga in** |
| Lyckad | Sidan efter inloggning har butiksväljaren `#ctl00_ddlSitePicker` |

Det är en personlig inloggning (e-post och lösenord), inte API-nyckeln. Webbshop-ID är troligen samma värde som användarnamnet i REST-API:ts Basic-auth (`webshopId` i kontot), men det är **[overifierat]**. Ett webbshop-ID omfattar flera webbplatser. En instans kan till exempel ha en butik per land.

## Butiksväljaren

| | |
|---|---|
| Element | `<select id="ctl00_ddlSitePicker">` |
| Options | Webbplatsnamn, standardbutiken med suffix: `Butik SE (standard)`, `Butik DK`, `Butik FI`, `Butik NO`. Matcha med "börjar med". |
| Synlighet | **Dold** bakom E37:s egen dropdown. Den finns i DOM:en men syns inte. |
| Byte | Sätt `value` och skicka `change`, så görs en postback. Utan webbläsare blir det en POST med `__EVENTTARGET=ctl00$ddlSitePicker` och det nya värdet. |
| Kontroll | Läs vald option efter omladdningen. Står den inte på rätt butik, avbryt. |

Butiksvalet är sessionstillstånd på serversidan. Allt som görs efteråt gäller den valda webbplatsen.

## Artikelregistret

| | |
|---|---|
| Sida | `workspace/workwith/articles/list.aspx` |
| Sökfält | `#ctl00_cph1_settingstabs_tabSearch_txtSearch` |
| Sökknapp | `#btnArticleSearch` (postback) |
| Huvudartikel | `tr.articleMain`. Fälls ut med `img.articleExpander`, vars `src` innehåller `plus` när raden är hopfälld. |
| Variant | `tr.av a`. Länktexten är variantens exakta artikelnummer, t.ex. `18-30120542`. |

Sökningen matchar på delsträng. Kräv **exakt** träff på länktexten och exakt en sådan, annars hoppa över artikeln med ett fel. Att utfällningen sker i webbläsaren och inte som postback är **[overifierat]**. Visar det sig att varianterna redan finns i HTML:en kan en ren HTTP-klient läsa dem direkt.

## Variantdialogen

Öppnas genom att klicka på variantlänken. Det är en modal på samma sida, inte en ny URL.

| | |
|---|---|
| Rubrik | `Redigera artikelvariant - {artnr}` |
| Spara och stäng | `#ctl00_cph1_mod1_pnl_usrCtrl_btnSave` |
| Avbryt | `#ctl00_cph1_mod1_pnl_usrCtrl_btnCancel` |
| Stängd | Sparknappen blir dold |

`mod1_pnl_usrCtrl` tyder på en UserControl i en UpdatePanel, alltså en AJAX-postback. Det är troligen därför kartläggningen behövde en riktig webbläsare.

### Kända fält

| Fält i UI | Flik | Selektor | Anmärkning |
|---|---|---|---|
| Leverans-/beställningstid, om slut i lager (Alt. 2, fritext) | Lager | `input[type=text][id*="tbDeliveryTimeText_"]` vars id **inte** innehåller `InStock` | Språkbundet. Id:t slutar på språkkod, t.ex. `_sv`. Det finns ett syskonfält med `InStock` i id:t för leveranstid när varan finns i lager. |

Fälten skrivs genom att sätta `value` och skicka `input`, `change`, `keyup` och `blur`. E37 lyssnar på åtminstone ett av dem innan Spara tar värdet.

## Det som saknas i API:et

| Lucka | Varför webben | Källa |
|---|---|---|
| Läsa och skriva leveranstidstext per variant och webbplats | Fältet finns inte i Triton Admin REST API, som bara har ordrar och presentkort. Det finns inte heller i E37:s inbyggda export ("Exportera sökresultat", "Exportfiler"). | kartläggningen 2026-10-06 |
| Kampanjer, rabattkoder, taggar, attribut, sidor, innehållselement, widgets, tillval, matriser | Inget av det finns i REST API:t. | `registers.py`, 2026-10-09 |

Fyll på tabellen när fler luckor dyker upp. Varje funktion i `web.py` ska peka hit.

## Att bygga hos oss

Gjort som resten av `e37-cli`:

```
e37 web login-check                    logga in, lista webbplatserna, logga ut
e37 web delivery-text get ART...       läs fältet per webbplats, ändrar inget
e37 web delivery-text set FIL          sätt från CSV/xlsx (art-nr;datum), --dry-run först
    --sites SE,DK,FI,NO  --limit N  --log FIL.csv
```

- **Konto:** webbinloggningen finns redan i kontot, som `web: {"email", "password"}` i nyckelringsposten. Den fylls i med `e37 account add`. Webbshop-ID tas från `webshopId`. Aldrig i repot och aldrig i loggar eller felsökningsfiler.
- **Flera instanser samtidigt:** vi behöver vara inloggade i flera E37-instanser på en gång, till exempel två bolags butiker. Varje instans är en egen post i nyckelringen med eget webbshop-ID, egen server (admin2 eller admin3) och egen inloggning. Därför:
  - **En session per konto.** Det är ett eget `Session`-objekt med egen cookie-jar. Ingenting i `web.py` får vara global state, så att två konton kan köras i samma process eller i varsin.
  - **Butiksvalet sitter i sessionen på serversidan.** Två jobb mot samma konto som delar session byter butik under fötterna på varandra, och det märks inte förrän fel butik har fått en ändring. Varje körning loggar därför in i en egen session och delar den inte. Kontrollera butiksvalet igen innan varje skrivning, inte bara efter bytet.
  - **Sessioner sparas inte mellan körningar** i första versionen. Inloggningen är ett enda POST-anrop. Behövs det senare, lägg sessionscookien i nyckelringen bredvid kontot, inte i en fil.
  - **`--account` är obligatoriskt** för `e37 web` när fler än ett konto är konfigurerat, precis som för `e37 order`. Ingen standardinstans, eftersom en skrivning mot fel instans är det värsta felet modulen kan göra.
  - **Varje loggrad, CSV-rad och felsökningsfil** tar med kontonamnet, inte bara webbplatsen. Två instanser kan ha webbplatser med samma namn.
- **Webbplatser och texter:** mallen per webbplats (`Förväntas åter i lager: {date}` och så vidare) är data, inte kod. Lägg den i kontot, eftersom texterna är butikens egna.
- **Motor:** Scrapling, `e37-cli[web]`. Pröva i den här ordningen:
  1. `Fetcher` med session och ren POST: inloggning, butiksbyte och sök är vanliga postbacks och bör gå utan webbläsare. Billigt och snabbt, och fungerar på en server.
  2. Variantdialogen är troligen en UpdatePanel. Den går att posta direkt (`ScriptManager`-fältet, `__ASYNCPOST=true`, svaret i `|`-separerat delta-format), men det är skört. Fungerar det inte, ta `DynamicFetcher` med `page_action` för just det steget.
- **Säkerhet vid skrivning**, samma regler som i resten av paketet:
  - `--dry-run` är standard för ny logik. Kör först med `--limit 2`.
  - Läs tillbaka varje sparat värde. Avvikelse blir `FEL: sparat värde är '...'`.
  - Ett fel på en artikel loggas och körningen går vidare. Exit 1 om något fel uppstod.
  - CSV-logg med webbplats, artikel, gammalt värde, nytt värde och status, `;`-separerad, utf-8-sig, så att Excel öppnar den rätt.
  - Hoppa över det som redan har rätt värde (`oförändrad`) i stället för att spara igen.
- **Excel utan pandas:** en xlsx-fil är en zip med XML. Två kolumner går att läsa med `zipfile` och `xml.etree`. Tar vi CSV också slipper användaren konvertera.
- **Felsökning:** spara HTML (inte skärmbilder) i `logs/` när något går fel. Töm lösenordsfält först.

## Regler

- Använd bara för det som saknas i `admin.py`.
- Dokumentera varje funktion med vilken lucka i API:et den täcker, så att den kan tas bort när API:et hinner ikapp.
- Hantera att ViewState blir ogiltig (session löpt ut, sida ändrad). Logga in igen och hämta om sidan i stället för att krascha.
- Spara aldrig sessioncookies eller inloggningsuppgifter i repot.
