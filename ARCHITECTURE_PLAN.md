# Studie+ Schedule API Architecture Plan

## Overview
Redesign of schedule/homework scraping to provide comprehensive, well-structured schedule data with homework, notes, and file attachments.

## Core Design Principles
1. **Separation of Concerns**: Parse schedule → Extract details → Fetch files
2. **Reusability**: General parsers that can be filtered/transformed
3. **Complete Data**: Include all metadata (dates, weekdays, colors, etc.)
4. **Flexibility**: Support week navigation and date filtering

---

## Data Structures

### Lesson (Basic)
```python
{
    "id": "2025-11-11_08:15",  # Unique: date + time
    "date": "2025-11-11",      # ISO format
    "weekday": "Mandag",
    "time": "08:15-09:15",
    "subject": "Fysik A",
    "teacher": "piat",
    "room": "M1304",
    "has_homework": True,
    "has_note": False,
    "has_files": True
}
```

### Lesson Details (Extended)
```python
{
    # All fields from Lesson (Basic)
    "homework": "Fremlæggelse af rapporter...",
    "note": "",
    "files": [
        {
            "name": "rapport.pdf",
            "url": "https://...",
            "size": "1.2 MB"  # If available
        }
    ]
}
```

---

## Scraper Functions (src/studieplus_scraper/scraper.py)

### 1. Core Parser
```python
async def parse_schedule(self, week_offset: int = 0) -> List[Dict]:
    """
    Parse the entire weekly schedule and return ALL lessons with metadata.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

    Returns:
        List of lessons (Basic format)

    Implementation:
        1. Navigate to week (if offset != 0)
        2. Get HTML content
        3. Extract week dates from <div class="gwt-Label">
        4. Parse all SVG <g class="CAHE1CD-h-b"> elements
        5. Match x-position to weekday (x/197 = day index)
        6. Calculate date from week start + day index
        7. Extract: time, subject, teacher, room
        8. Check for homework/notes/files in title tags
        9. Return complete lesson list
    """
```

### 2. Detail Extractor
```python
async def get_lesson_details(self, date: str, time: str) -> Dict:
    """
    Get homework, notes, and files for a specific lesson.

    Args:
        date: ISO format (YYYY-MM-DD)
        time: Time range (HH:MM-HH:MM)

    Returns:
        Lesson Details (Extended format)

    Implementation:
        1. Navigate to correct week (from date)
        2. Find lesson by date+time
        3. Click lesson with force=True
        4. Press Ctrl+Alt+N to open info panel
        5. Parse info panel for:
           - Full homework text
           - Full note text
           - File links and metadata
        6. Return extended lesson data
    """
```

### 3. Week Navigation Helper
```python
async def navigate_to_week(self, week_offset: int):
    """
    Navigate to a specific week.

    Args:
        week_offset: Weeks from current

    Implementation:
        - Click chevron-right button (week_offset times) if positive
        - Click chevron-left button (abs(week_offset) times) if negative
    """
```

### 4. Date Parser Helper
```python
def parse_week_dates(self, soup: BeautifulSoup) -> List[str]:
    """
    Extract dates for the week from HTML.

    Returns:
        ["2025-11-10", "2025-11-11", ...] # 7 dates

    Implementation:
        1. Find all <div class="gwt-Label"> with pattern "Man DD/MM"
        2. Extract year from "Uge XX - YYYY" button
        3. Convert to ISO dates
    """
```

### 5. SVG Position Calculator
```python
def calculate_lesson_date(self, transform: str, week_dates: List[str]) -> str:
    """
    Calculate lesson date from SVG transform position.

    Args:
        transform: "translate(394, 600) rotate(0)"
        week_dates: List of ISO dates for the week

    Returns:
        ISO date string

    Implementation:
        - Parse x-position from transform
        - day_index = x // 197
        - return week_dates[day_index]
    """
```

---

## MCP Server Tools (src/mcp_server/server.py)

### 1. Get Full Schedule
```python
@mcp.tool()
async def get_schedule(week_offset: int = 0, include_details: bool = False) -> dict:
    """
    Get complete weekly schedule.

    Args:
        week_offset: Weeks from current (default: 0)
        include_details: Include homework/notes/files (default: False)

    Returns:
        {
            "week": "46",
            "year": "2025",
            "dates": ["2025-11-10", "2025-11-11", ...],
            "lessons": [Lesson (Basic) or Lesson (Extended) if include_details]
        }
    """
```

### 2. Get Homework Overview
```python
@mcp.tool()
async def get_homework_overview(week_offset: int = 0, days_ahead: int = 7) -> dict:
    """
    Get lessons with homework or notes.

    Args:
        week_offset: Weeks from current
        days_ahead: How many days to look ahead (from today)

    Returns:
        {
            "count": 5,
            "lessons": [Lesson (Extended) - only with homework/notes]
        }

    Implementation:
        1. Get full schedule
        2. Filter: has_homework OR has_note
        3. Filter by days_ahead (from current date)
        4. Fetch details for each lesson
        5. Return extended data
    """
```

### 3. Get Lesson Details
```python
@mcp.tool()
async def get_lesson_details(date: str, time: str) -> dict:
    """
    Get details for a specific lesson.

    Args:
        date: ISO format (YYYY-MM-DD)
        time: Time range (HH:MM-HH:MM)

    Returns:
        Lesson (Extended)
    """
```

### 4. Download Lesson Files (Future)
```python
@mcp.tool()
async def download_lesson_files(
    date: str,
    time: str,
    output_dir: str = "./downloads"
) -> dict:
    """
    Download all files for a lesson.

    Returns:
        {
            "downloaded": 3,
            "files": [
                {
                    "name": "rapport.pdf",
                    "path": "./downloads/2025-11-11_Fysik_rapport.pdf",
                    "size": "1.2 MB"
                }
            ]
        }
    """
```

---

---

## API Layer (src/studieplus_scraper/api.py)

**Purpose**: Business logic mellem scraper og MCP. Håndterer data transformation, filtering, og scraper lifecycle.

### 1. Schedule API
```python
async def get_full_schedule(week_offset: int = 0) -> dict:
    """
    Get complete weekly schedule with all lessons.

    Args:
        week_offset: Weeks from current

    Returns:
        {
            "week": "46",
            "year": "2025",
            "dates": ["2025-11-10", ...],
            "lessons": [Lesson (Basic)]
        }

    Implementation:
        1. Create scraper instance
        2. Call scraper.parse_schedule(week_offset)
        3. Format response
        4. Clean up scraper
    """
```

### 2. Homework API
```python
async def get_homework_and_notes(
    week_offset: int = 0,
    days_ahead: int = 7,
    include_details: bool = True
) -> dict:
    """
    Get lessons with homework or notes.

    Args:
        week_offset: Weeks from current
        days_ahead: Filter by days from today
        include_details: Fetch full homework/notes text

    Returns:
        {
            "count": 5,
            "lessons": [Lesson (Basic) or (Extended)]
        }

    Implementation:
        1. Create scraper
        2. Get schedule via scraper.parse_schedule()
        3. Filter: has_homework OR has_note
        4. Filter by days_ahead (from datetime.now())
        5. If include_details: fetch details for each
        6. Return filtered list
    """
```

### 3. Lesson Detail API
```python
async def get_lesson_detail(date: str, time: str) -> dict:
    """
    Get full details for a specific lesson.

    Args:
        date: ISO format
        time: HH:MM-HH:MM

    Returns:
        Lesson (Extended)

    Implementation:
        1. Create scraper
        2. Call scraper.get_lesson_details(date, time)
        3. Return formatted response
    """
```

### 4. File Download API (Future)
```python
async def download_files_for_lesson(
    date: str,
    time: str,
    output_dir: str = "./downloads"
) -> dict:
    """
    Download all files for a lesson.

    Returns:
        {
            "downloaded": 3,
            "files": [...]
        }
    """
```

---

## Updated MCP Server Tools

**Purpose**: Thin wrapper around API layer. Handles MCP-specific formatting only.

### 1. Get Schedule
```python
@mcp.tool()
async def get_schedule(week_offset: int = 0) -> dict:
    """Get complete weekly schedule."""
    from studieplus_scraper.api import get_full_schedule
    return await get_full_schedule(week_offset=week_offset)
```

### 2. Get Homework Overview
```python
@mcp.tool()
async def get_homework_overview(
    week_offset: int = 0,
    days_ahead: int = 7
) -> dict:
    """Get lessons with homework or notes."""
    from studieplus_scraper.api import get_homework_and_notes
    return await get_homework_and_notes(
        week_offset=week_offset,
        days_ahead=days_ahead,
        include_details=True
    )
```

### 3. Get Lesson Details
```python
@mcp.tool()
async def get_lesson_details(date: str, time: str) -> dict:
    """Get details for a specific lesson."""
    from studieplus_scraper.api import get_lesson_detail
    return await get_lesson_detail(date=date, time=time)
```

---

## Layer Responsibilities

### Scraper Layer (scraper.py)
- ✅ Playwright browser automation
- ✅ Raw HTML/SVG parsing
- ✅ Navigation (login, week switching)
- ✅ Data extraction
- ❌ NO business logic
- ❌ NO data filtering
- ❌ NO response formatting

### API Layer (api.py)
- ✅ Scraper lifecycle management
- ✅ Business logic (filtering, sorting)
- ✅ Data transformation
- ✅ Date calculations
- ✅ Error handling
- ✅ Response formatting
- ❌ NO MCP-specific code

### MCP Layer (server.py)
- ✅ MCP tool definitions
- ✅ Parameter validation
- ✅ Documentation (docstrings)
- ❌ NO business logic
- ❌ NO scraper access (use API only)

---

## Implementation Steps

### Phase 1: Basic Schedule Parser ✅ Priority
1. ✅ Implement `parse_week_dates()` helper
2. ✅ Implement `calculate_lesson_date()` helper
3. ✅ Implement `navigate_to_week()` helper
4. ✅ Refactor existing SVG parsing into `parse_schedule()`
5. ✅ Update to return Lesson (Basic) format with dates
6. ✅ Test with current week and week_offset

### Phase 2: Detail Extraction
1. Implement `get_lesson_details()` with click + Ctrl+Alt+N
2. Parse info panel HTML for homework/notes
3. Extract file information from info panel
4. Test with lessons that have files

### Phase 3: MCP Tools
1. Update `get_schedule()` MCP tool
2. Create `get_homework_overview()` MCP tool
3. Create `get_lesson_details()` MCP tool
4. Deprecate old `get_schedule_homework()` tool

### Phase 4: File Downloads (Optional)
1. Implement file download logic
2. Create `download_lesson_files()` tool
3. Add file size detection

---

## Migration Strategy

### Current Function
```python
get_schedule_homework() -> dict
# Returns only lessons with homework/notes
# No dates, limited metadata
```

### New Functions
```python
get_schedule(week_offset=0) -> dict
# Returns ALL lessons with dates

get_homework_overview(week_offset=0, days_ahead=7) -> dict
# Replaces get_schedule_homework()
# More flexible filtering
```

### Backward Compatibility
Keep `get_schedule_homework()` as alias:
```python
@mcp.tool()
async def get_schedule_homework() -> dict:
    """Deprecated: Use get_homework_overview() instead"""
    return await get_homework_overview(week_offset=0, days_ahead=7)
```

---

## Testing Checklist

- [ ] Parse current week schedule
- [ ] Navigate to next week (week_offset=1)
- [ ] Navigate to previous week (week_offset=-1)
- [ ] Correctly match dates to lessons
- [ ] Extract homework text
- [ ] Extract note text
- [ ] Click lesson and open info panel
- [ ] Parse file information from info panel
- [ ] Handle lessons without homework/notes
- [ ] Handle weekend days correctly
- [ ] Test with Danish and English strings

---

## Open Questions

1. ✅ **Lesson ID format**: Using "date_time" (e.g., "2025-11-11_08:15")
2. ❓ **File downloads**: Where to store? How to name?
3. ❓ **Info panel timeout**: How long to wait after Ctrl+Alt+N?
4. ❓ **Multiple files per lesson**: How to detect all files?
5. ❓ **URL for week navigation**: Can we use URL params instead of clicking?

---

## Next Steps

1. Start with **Phase 1**: Implement basic schedule parser with dates
2. Test thoroughly with different weeks
3. Move to **Phase 2**: Detail extraction
4. Get your feedback before Phase 3
