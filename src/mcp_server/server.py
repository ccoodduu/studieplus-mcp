import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.append(str(Path(__file__).parent.parent))

from studieplus_scraper import api
from fastmcp import FastMCP

# System instructions for LLMs using this MCP server
SYSTEM_INSTRUCTIONS = """
Du har adgang til en dansk elevs skoledata fra Studie+.

VIGTIGE BEGREBER:
- AFLEVERINGER = Formelle opgaver med deadlines (fra Opgaver-siden)
- LEKTIER = Daglige lektier fra skemaet (blå felter i skemaet)
- NOTER = Beskeder/info fra lærere i skemaet (grønne felter)

START HER:
- "Hvad har jeg i dag/i morgen?" → get_day_overview(day_offset=0 eller 1)
- "Hvad skal jeg aflevere?" → get_assignments()
- "Overblik over ugen?" → get_week_overview()

PARAMETRE:
- day_offset: 0=i dag, 1=i morgen, -1=i går, 2=i overmorgen, osv.
- week_offset: 0=denne uge, 1=næste uge, -1=sidste uge

TYPISKE SPØRGSMÅL:
- "Hvilket lokale skal jeg møde i?" → get_day_overview(), tjek first_lesson.room
- "Hvornår starter jeg?" → get_day_overview(), tjek first_lesson.time
- "Har jeg lektier for?" → get_day_overview(), tjek homework listen
- "Hvad har jeg misset?" → get_week_overview(week_offset=-1)
"""

mcp = FastMCP("Studie+ Skole Assistent", instructions=SYSTEM_INSTRUCTIONS)


# Danish weekday and month names for formatting
WEEKDAYS_DA = {
    0: "Mandag", 1: "Tirsdag", 2: "Onsdag", 3: "Torsdag",
    4: "Fredag", 5: "Lørdag", 6: "Søndag"
}

MONTHS_DA = {
    1: "januar", 2: "februar", 3: "marts", 4: "april",
    5: "maj", 6: "juni", 7: "juli", 8: "august",
    9: "september", 10: "oktober", 11: "november", 12: "december"
}


def format_datetime_for_claude(dt: datetime = None, include_time: bool = True) -> str:
    """Format datetime in a clear, readable format for Claude."""
    if dt is None:
        dt = datetime.now()

    weekday = WEEKDAYS_DA[dt.weekday()]
    day = dt.day
    month = MONTHS_DA[dt.month]
    year = dt.year
    week = dt.isocalendar()[1]

    if include_time:
        time_str = dt.strftime("%H:%M")
        return f"{weekday} {day}. {month} {year}, uge {week}, kl. {time_str}"
    else:
        return f"{weekday} {day}. {month} {year}, uge {week}"


def format_date_string(date_str: str, include_time: bool = False) -> str:
    """Convert ISO or Danish format date string to Claude-friendly format."""
    try:
        if include_time and ' ' in date_str:
            # Danish format: "16.11.2025 08:00"
            dt = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
        elif '-' in date_str:
            # ISO format: "2025-11-12"
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            return date_str

        return format_datetime_for_claude(dt, include_time=include_time)
    except Exception:
        return date_str


def clean_for_llm(data: dict | list) -> dict | list:
    """
    Remove false boolean fields and empty strings from data to reduce LLM token usage.
    Recursively cleans nested dicts and lists.
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            # Skip false booleans and empty strings
            if value is False or value == "":
                continue
            # Recursively clean nested structures
            if isinstance(value, (dict, list)):
                cleaned[key] = clean_for_llm(value)
            else:
                cleaned[key] = value
        return cleaned
    elif isinstance(data, list):
        return [clean_for_llm(item) if isinstance(item, (dict, list)) else item for item in data]
    return data


# ==================== MAIN TOOLS ====================

@mcp.tool()
async def get_day_overview(day_offset: int = 0) -> dict:
    """
    Få overblik over en bestemt dag: skema, lektier, noter, og afleveringer.

    Brug denne til spørgsmål som:
    - "Hvad har jeg i dag?" (day_offset=0)
    - "Har jeg lektier til i morgen?" (day_offset=1)
    - "Hvilket lokale skal jeg møde i?" (day_offset=0, tjek first_lesson)
    - "Hvornår starter jeg i morgen?" (day_offset=1, tjek first_lesson)

    Args:
        day_offset: Dage fra i dag (0=i dag, 1=i morgen, -1=i går)

    Returns:
        - date: Dato (YYYY-MM-DD)
        - weekday: Ugedag på dansk
        - lessons: Liste af lektioner med tid, fag, lærer, lokale
        - homework: Lektioner med lektier
        - notes: Lektioner med noter
        - assignments_due: Afleveringer med deadline den dag
        - first_lesson: Første lektion (tid, lokale, fag)
        - last_lesson: Sidste lektion (tid, lokale, fag)
    """
    result = await api.get_day_overview(day_offset=day_offset)

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    # Format date
    if result.get('date'):
        result['date_formatted'] = format_date_string(result['date'], include_time=False)

    return clean_for_llm(result)


@mcp.tool()
async def get_week_overview(week_offset: int = 0) -> dict:
    """
    Få overblik over en hel uge: skema, lektier, noter, og afleveringer.

    Brug denne til spørgsmål som:
    - "Hvad har jeg i denne uge?" (week_offset=0)
    - "Hvad har jeg misset sidste uge?" (week_offset=-1)
    - "Overblik over næste uge?" (week_offset=1)

    Args:
        week_offset: Uger fra nu (0=denne uge, 1=næste uge, -1=sidste uge)

    Returns:
        - week: Uge nummer og år (f.eks. "4/2026")
        - days: Liste af dage med lektioner
        - homework_count: Antal lektioner med lektier
        - notes_count: Antal lektioner med noter
        - assignments: Afleveringer med deadline i ugen
    """
    result = await api.get_week_overview(week_offset=week_offset)

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    # Format dates in days
    for day in result.get('days', []):
        if day.get('date'):
            day['date_formatted'] = format_date_string(day['date'], include_time=False)

    return clean_for_llm(result)


@mcp.tool()
async def get_assignments(
    include_submitted: bool = False,
    days_ahead: Optional[int] = None,
    subject: Optional[str] = None
) -> dict:
    """
    Hent afleveringer (formelle opgaver med deadlines).

    Brug denne til spørgsmål som:
    - "Hvad skal jeg aflevere?" (ingen filtre)
    - "Hvad er min næste aflevering?" (days_ahead=30, tag første)
    - "Har jeg dansk afleveringer?" (subject="Dansk")
    - "Vis alle mine afleveringer" (include_submitted=True)

    Args:
        include_submitted: Inkluder allerede afleverede (default: kun åbne)
        days_ahead: Kun afleveringer med deadline inden for N dage
        subject: Filtrer på fag (f.eks. "Dansk", "Matematik")

    Returns:
        - count: Antal afleveringer
        - assignments: Liste med subject, title, deadline, submitted, row_index
    """
    result = await api.get_assignments_filtered(
        include_submitted=include_submitted,
        days_ahead=days_ahead,
        subject=subject
    )

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    # Format deadlines
    for assignment in result.get('assignments', []):
        if assignment.get('deadline'):
            assignment['deadline_formatted'] = format_date_string(
                assignment['deadline'], include_time=True
            )

    return clean_for_llm(result)


@mcp.tool()
async def get_assignment_details(row_index: str) -> dict:
    """
    Hent detaljer om en specifik aflevering inkl. beskrivelse og filer.

    Brug row_index fra get_assignments() resultatet.

    Args:
        row_index: Afleveringens row_index (fra get_assignments)

    Returns:
        - assignment_title: Titel
        - subject: Fag
        - description: Beskrivelse (HTML)
        - deadline: Afleveringsfrist
        - files: Liste af filer med navn og URL
        - submission_status: Afleveret/Ikke afleveret
    """
    result = await api.get_assignment_detail(row_index=row_index)

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    # Format deadline
    if result.get('deadline'):
        result['deadline_formatted'] = format_date_string(result['deadline'], include_time=True)

    return clean_for_llm(result)


@mcp.tool()
async def get_lesson_files(lesson_id: int) -> dict:
    """
    Hent filer fra en lektion med download URLs.

    Brug lesson_id fra get_day_overview() eller get_week_overview().

    Args:
        lesson_id: Lektionens ID (fra lessons i day/week overview)

    Returns:
        - lesson_id: Lektionens ID
        - count: Antal filer
        - files: Liste med name, id, url (signeret S3 URL, gyldig ~5 min)
    """
    result = await api.get_lesson_files(lesson_id=lesson_id)

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    return result


@mcp.tool()
async def download_lesson_file(file_url: str, file_name: str, output_dir: str = "./downloads") -> dict:
    """
    Download en fil fra en lektion til downloads mappen.

    Args:
        file_url: URL til filen (fra get_lesson_files)
        file_name: Filens navn
        output_dir: Mappe at gemme i (default: ./downloads)

    Returns:
        - success: Om download lykkedes
        - file_path: Sti til den downloadede fil
        - file_size: Filstørrelse i bytes
    """
    result = await api.download_file(
        file_url=file_url,
        file_name=file_name,
        output_dir=output_dir
    )

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    return result


@mcp.tool()
async def load_lesson_file(file_url: str, file_name: str) -> dict:
    """
    Indlæs en fil og returner indholdet så du kan læse det.

    Args:
        file_url: URL til filen (fra get_lesson_files)
        file_name: Filens navn

    Returns:
        - success: Om indlæsning lykkedes
        - content: Filindhold (tekst eller base64)
        - content_type: MIME type
        - is_text: Om filen er tekst-baseret
    """
    result = await api.load_file(
        file_url=file_url,
        file_name=file_name
    )

    # Add current time context
    result['current_time'] = format_datetime_for_claude()

    return result


if __name__ == "__main__":
    # Support both stdio (Claude Desktop) and SSE (Docker/Pi) transports
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MCP_PORT", "8101"))

    if transport == "sse":
        mcp.run(transport="sse", port=port)
    else:
        mcp.run()  # Default: stdio for Claude Desktop
