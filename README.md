# e37

Samlingsrepo för allt som rör E37: integrationer mot deras API, MCP-server, dokumentation och skript.

## Innehåll

| Sökväg | Beskrivning |
|---|---|
| `docs/` | Anteckningar, API-dokumentation och beslut |
| `.env.example` | Mall för miljövariabler (nycklar, endpoints). Kopiera till `.env`, som är gitignorerad |

Mer läggs till efterhand (API-klient, MCP-server osv.).

## Kom igång

```sh
cp .env.example .env
# fyll i värden i .env
```

## Hemligheter

Inga nycklar eller tokens checkas in. Lägg dem i `.env` lokalt eller i `wesports-secrets`.
