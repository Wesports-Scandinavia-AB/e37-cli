# client

Klienter mot E37. Används av `mcp/` och eventuella andra konsumenter.

| Sökväg | Beskrivning |
|---|---|
| `api/` | Typad klient mot E37:s officiella API |
| `web/` | Klient som automatiserar E37:s webbgränssnitt, för sådant som inte finns i API:et |

Föredra alltid `api/` när funktionen finns där. `web/` är för luckor i API:et och är skörare, eftersom den bryter när E37 ändrar sin webb.
