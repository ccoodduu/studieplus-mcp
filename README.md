# Studie+ MCP Server 🎒

MCP server for checking homework from Studie+ (Danish education platform). Works seamlessly with Claude Desktop to check your assignments!

## Features

✅ **Check all homework** - Get complete list of assignments from Assignments page
✅ **Schedule homework** - Get homework and notes directly from the weekly schedule (skema)
✅ **Upcoming deadlines** - Filter by deadline (next 7 days, etc.)
✅ **Filter by subject** - See assignments for specific subjects
✅ **Assignment details** - Get full description and files for any assignment
✅ **Headless scraping** - No browser window, runs in background
✅ **Fast & efficient** - Optimized Playwright scraper

## Setup

### 1. Install Dependencies

```bash
cd studieplus-mcp
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Credentials

Create `.env` file:
```
STUDIEPLUS_USERNAME=your_username
STUDIEPLUS_PASSWORD=your_password
STUDIEPLUS_SCHOOL=DIN_SKOLE
```

### 3. Test the Scraper

```bash
python src/studieplus_scraper/scraper.py
```

### 4. Add to Claude Desktop

Edit Claude Desktop config file:
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add this configuration:

```json
{
  "mcpServers": {
    "studieplus": {
      "command": "python",
      "args": [
        "C:/Users/willi/mcp-servers/studieplus-mcp/src/mcp_server/server.py"
      ],
      "env": {
        "STUDIEPLUS_USERNAME": "your_username",
        "STUDIEPLUS_PASSWORD": "your_password",
        "STUDIEPLUS_SCHOOL": "DIN_SKOLE"
      }
    }
  }
}
```

**⚠️ IMPORTANT**: Update the path in `args` to match your actual installation directory!

### 5. Restart Claude Desktop

Restart Claude Desktop to load the MCP server.

## Usage in Claude

Once installed, you can ask Claude:

- "Hvad er mine lektier?" (What's my homework?)
- "Hvilke opgaver har jeg i matematik?" (What assignments do I have in math?)
- "Hvad skal jeg lave i de næste 7 dage?" (What do I need to do in the next 7 days?)
- "Har jeg deadlines snart?" (Do I have upcoming deadlines?)

## Available MCP Tools

1. **`get_homework()`** - Get all homework assignments
2. **`get_upcoming_homework(days=7)`** - Get assignments due within N days
3. **`get_homework_by_subject(subject)`** - Filter assignments by subject
4. **`get_assignment_details(assignment_id)`** - Get detailed info (description & files) for a specific assignment

## Components

- **src/studieplus_scraper/scraper.py**: Playwright-based headless scraper
- **src/mcp_server/server.py**: MCP server with FastMCP
- **analyze_traffic.py**: Network traffic analyzer (dev tool)
