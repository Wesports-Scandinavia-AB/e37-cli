# e37

Samlingsrepo för allt som rör E37: integrationer mot deras API, MCP-server, dokumentation och skript.

## Innehåll

| Sökväg | Beskrivning |
|---|---|
| `client/api/` | Typad klient mot E37:s officiella API |
| `client/web/` | Klient mot E37:s webbgränssnitt, för sådant som saknas i API:et |
| `mcp/` | MCP-server som använder `client/` |
| `docs/` | Dokumentation: Order-API, OpenAPI-spec, MCP. Börja i `docs/README.md` |
| `.env.example` | Mall för miljövariabler (nycklar, endpoints). Kopiera till `.env`, som är gitignorerad |

Strukturen är platt medvetet. Om ett tredje paket dyker upp flyttas allt till `packages/`.

## Kom igång

```sh
cp .env.example .env
# fyll i värden i .env
```

## Hemligheter

Inga nycklar eller tokens checkas in. Lägg dem i `.env` lokalt eller i `wesports-secrets`.
