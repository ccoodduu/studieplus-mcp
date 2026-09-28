# Studie+ MCP Server

MCP server der giver Claude Desktop (og andre MCP-klienter) adgang til skoledata fra [Studie+](https://studieplus.dk) — den danske skoleplatform.

Spørg Claude om dit skema, lektier, afleveringer og filer direkte i chatten.

Al kommunikation med Studie+ ligger i [studieplus-api](https://github.com/ccoodduu/studieplus-api). Vil du have skemaet og afleveringerne i Google Kalender, så se [studieplus-calendar](https://github.com/ccoodduu/studieplus-calendar).

## Features

- **Dagsoverblik** — skema, lektier, noter og afleveringer for en given dag
- **Ugeoverblik** — komplet ugeskema med lektier og deadlines
- **Afleveringer** — filtrer på fag, deadline, eller vis alle
- **Afleveringsdetaljer** — beskrivelse, filer og status
- **Lektionsfiler** — hent filer fra lektioner med signerede download-URLs
- **Fil-download** — download filer direkte til din computer
- **Letvægts-scraper** — bruger HTTP direkte (ingen browser, ~30MB RAM)
- **Cross-platform** — virker på Windows, Mac og Linux

## Setup

### 1. Installer dependencies

```bash
cd studieplus-mcp
pip install -r requirements.txt
```

Det installerer også nyeste `studieplus-api` fra GitHub. Opdatér den senere med:

```bash
pip install --force-reinstall --no-deps "studieplus-api @ git+https://github.com/ccoodduu/studieplus-api"
```

### 2. Konfigurer credentials

Opret en `.env` fil:
```
STUDIEPLUS_USERNAME=dit_brugernavn
STUDIEPLUS_PASSWORD=dit_kodeord
STUDIEPLUS_SCHOOL=DIN_SKOLE
```

### 3. Tilføj til Claude Desktop

Rediger Claude Desktop config:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "studieplus": {
      "command": "python",
      "args": [
        "/sti/til/studieplus-mcp/src/mcp_server/server.py"
      ],
      "env": {
        "STUDIEPLUS_USERNAME": "dit_brugernavn",
        "STUDIEPLUS_PASSWORD": "dit_kodeord",
        "STUDIEPLUS_SCHOOL": "DIN_SKOLE"
      }
    }
  }
}
```

> Udskift `/sti/til/studieplus-mcp` med den faktiske sti til projektet.

### 4. Genstart Claude Desktop

Genstart Claude Desktop for at indlæse MCP serveren.

## Brug

Når serveren er installeret, kan du spørge Claude:

- "Hvad har jeg i dag?"
- "Har jeg lektier til i morgen?"
- "Hvad skal jeg aflevere?"
- "Hvilket lokale skal jeg møde i?"
- "Hvornår starter jeg i morgen?"
- "Har jeg dansk afleveringer?"
- "Hvad har jeg i næste uge?"
- "Download filerne fra min dansktime"

## MCP Tools

| Tool | Beskrivelse |
|------|-------------|
| `get_day_overview(day_offset)` | Skema, lektier, noter og afleveringer for en dag |
| `get_week_overview(week_offset)` | Komplet ugeoverblik |
| `get_assignments(include_submitted, days_ahead, subject)` | Afleveringer med filtrering |
| `get_assignment_details(assignment_id)` | Detaljer for en specifik aflevering |
| `get_lesson_files(lesson_id)` | Filer fra en lektion med download-URLs |
| `download_lesson_file(file_url, file_name)` | Download en fil til brugerens computer |
| `load_lesson_file(file_url, file_name)` | Indlæs filindhold direkte |

## Arkitektur

```
src/
  mcp_server/
    server.py              # MCP tools (thin wrapper)
    api.py                 # API lag (business logic, caching)
```

Selve scraperen (GWT-RPC-klienten) er pakken `studieplus_api` fra [studieplus-api](https://github.com/ccoodduu/studieplus-api). Den taler direkte med Studie+, og der skal ingen browser til.

## Transport

Serveren understøtter to transport-modes:

- **stdio** (default) — til Claude Desktop
- **SSE** — til Docker/Raspberry Pi deployment

```bash
# SSE mode
MCP_TRANSPORT=sse MCP_PORT=8101 python src/mcp_server/server.py
```

## Licens

MIT
