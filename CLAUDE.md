# StudiePlus MCP Server - Projektviden

## Projekt

MCP server der giver Claude Desktop adgang til en dansk elevs skoledata fra Studie+.

Al kommunikation med Studie+ (GWT-RPC, deserializers, login) ligger i
[studieplus-api](https://github.com/ccoodduu/studieplus-api), pakken `studieplus_api`.
**GWT-rettelser laves der, ikke her** — se dens `CLAUDE.md` for formatet og hvordan man
reverse engineerer nye typer. Lokalt ligger den i `../studieplus-api`.

`requirements.txt` følger bevidst nyeste `master` af studieplus-api. Lokalt er den
installeret editable i `.venv` (`uv pip install -e ../studieplus-api`), så ændringer i
api'en slår igennem med det samme.

Skema/afleveringer i Google Kalender er et separat projekt:
[studieplus-calendar](https://github.com/ccoodduu/studieplus-calendar) (`../studieplus-calendar`).

## Vigtige Filer

- `src/mcp_server/server.py` — MCP server tools. Claude Desktop starter den med
  `.venv\Scripts\python.exe src\mcp_server\server.py` — behold den sti.
- `src/mcp_server/api.py` — API lag mellem studieplus-api og MCP (dags/ugeoverblik, cache)
