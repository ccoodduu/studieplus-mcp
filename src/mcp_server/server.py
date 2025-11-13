import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))

from studieplus_scraper import api
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Studie+ Homework Checker")


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


# ==================== ASSIGNMENTS (Afleveringer fra Opgaver-siden) ====================

@mcp.tool()
async def get_assignments() -> dict:
    """
    Get all assignments (afleveringer) from the Opgaver page in Studie+.

    These are formal assignments with deadlines, not daily homework from schedule.

    Returns a dictionary with:
    - current_time: Current date and time for Claude's context
    - count: Total number of assignments
    - assignments: List of assignments with subject, title, deadline, hours, etc.
    """
    result = await api.get_all_assignments()

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format deadlines in all assignments
    for assignment in result.get('assignments', []):
        if assignment.get('deadline'):
            assignment['deadline'] = format_date_string(assignment['deadline'], include_time=True)

    return result


@mcp.tool()
async def get_upcoming_assignments(days: int = 7) -> dict:
    """
    Get assignments (afleveringer) with deadlines within the next N days.

    Args:
        days: Number of days to look ahead (default: 7)

    Returns assignments due within the specified timeframe.
    """
    result = await api.get_upcoming_assignments(days=days)

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format deadlines in all assignments
    for assignment in result.get('assignments', []):
        if assignment.get('deadline'):
            assignment['deadline'] = format_date_string(assignment['deadline'], include_time=True)

    return result


@mcp.tool()
async def get_assignments_by_subject(subject: str) -> dict:
    """
    Get assignments (afleveringer) for a specific subject.

    Args:
        subject: The subject name (e.g., "Matematik", "Dansk", "Engelsk")

    Returns assignments filtered by subject.
    """
    result = await api.get_assignments_by_subject(subject=subject)

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format deadlines in all assignments
    for assignment in result.get('assignments', []):
        if assignment.get('deadline'):
            assignment['deadline'] = format_date_string(assignment['deadline'], include_time=True)

    return result


@mcp.tool()
async def get_assignment_details(row_index: str) -> dict:
    """
    Get detailed information about a specific assignment (aflevering).

    Args:
        row_index: The row index of the assignment (from the 'row_index' field)

    Returns detailed information including description, files, and submission status.
    """
    result = await api.get_assignment_detail(row_index=row_index)

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format deadline if present
    if result.get('deadline'):
        result['deadline'] = format_date_string(result['deadline'], include_time=True)

    return result



# ==================== HOMEWORK (Lektier fra skemaet) ====================

@mcp.tool()
async def get_schedule(week_offset: int = 0) -> dict:
    """
    Get complete weekly schedule with all lessons, dates, and metadata.

    Note: For most use cases, prefer get_homework_overview() or get_notes() which automatically
    handle multiple weeks. This function is useful when you need the full schedule for a specific week.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

    Returns a dictionary with:
    - current_time: Current date and time for Claude's context
    - week: Week number (e.g., "46")
    - year: Year (e.g., "2025")
    - dates: List of ISO dates for the week
    - lessons: List of all lessons with date, time, subject, teacher, room, and flags for homework/notes/files
    """
    result = await api.get_full_schedule(week_offset=week_offset)

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format dates in all lessons
    for lesson in result.get('lessons', []):
        if lesson.get('date'):
            lesson['date'] = format_date_string(lesson['date'], include_time=False)

    return result


@mcp.tool()
async def get_homework_overview(days_ahead: int = 7) -> dict:
    """
    Get daily homework (lektier) and notes from the schedule (skema).

    This extracts homework and notes directly from the colored lesson boxes in the schedule.
    These are NOT formal assignments/afleveringer - use get_assignments() for those.

    - Blue lessons indicate homework
    - Green lessons indicate notes/information

    Automatically fetches from multiple weeks if needed.

    Args:
        days_ahead: How many days to look ahead from today (default: 7, max: 30)

    Returns a dictionary with:
    - current_time: Current date and time for Claude's context
    - count: Number of lessons with homework or notes
    - lessons: List of lessons with homework/notes text (includes date, weekday, time, subject, teacher, room)
    """
    result = await api.get_homework_and_notes(
        days_ahead=days_ahead,
        include_details=True
    )

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format dates in all lessons
    for lesson in result.get('lessons', []):
        if lesson.get('date'):
            lesson['date'] = format_date_string(lesson['date'], include_time=False)

    return result


@mcp.tool()
async def get_notes(days_ahead: int = 7) -> dict:
    """
    Get notes (noter) from lessons in the schedule.

    This extracts notes directly from the green lesson boxes in the schedule.
    Green lessons indicate notes/information from teachers.

    Use this to find teacher notes, announcements, or information about lessons.

    Automatically fetches from multiple weeks if needed.

    Args:
        days_ahead: How many days to look ahead from today (default: 7, max: 30)

    Returns a dictionary with:
    - current_time: Current date and time for Claude's context
    - count: Number of lessons with notes
    - lessons: List of lessons with notes (includes date, weekday, time, subject, teacher, room, note text)
    """
    result = await api.get_notes_overview(
        days_ahead=days_ahead,
        include_details=True
    )

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format dates in all lessons
    for lesson in result.get('lessons', []):
        if lesson.get('date'):
            lesson['date'] = format_date_string(lesson['date'], include_time=False)

    return result


@mcp.tool()
async def get_lesson_details(date: str, time: str) -> dict:
    """
    Get detailed information for a specific lesson including full homework text, notes, and files.

    Args:
        date: ISO format date (YYYY-MM-DD, e.g., "2025-11-10")
        time: Time range (HH:MM-HH:MM, e.g., "08:15-09:15")

    Returns detailed lesson information including homework text, notes, and file attachments.
    """
    result = await api.get_lesson_detail(date=date, time=time)

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    # Format date if present
    if result.get('date'):
        result['date'] = format_date_string(result['date'], include_time=False)

    return result


@mcp.tool()
async def download_lesson_file(file_url: str, file_name: str, output_dir: str = "./downloads") -> dict:
    """
    Download a file from a lesson to the downloads folder.

    Args:
        file_url: URL of the file to download
        file_name: Name of the file
        output_dir: Directory to save the file (default: ./downloads)

    Returns a dictionary with:
    - success: Whether the download was successful
    - file_path: Path to the downloaded file
    - file_name: Name of the downloaded file
    - file_size: Size of the file in bytes
    """
    result = await api.download_file(
        file_url=file_url,
        file_name=file_name,
        output_dir=output_dir
    )

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    return result


@mcp.tool()
async def load_lesson_file(file_url: str, file_name: str) -> dict:
    """
    Load a file from a lesson and return its content for Claude to read.

    Args:
        file_url: URL of the file to load
        file_name: Name of the file

    Returns a dictionary with:
    - success: Whether the load was successful
    - file_name: Name of the file
    - content: File content (text or base64 encoded)
    - content_type: MIME type of the file
    - size: Size of the file in bytes
    - is_text: Whether the file is text-based
    """
    result = await api.load_file(
        file_url=file_url,
        file_name=file_name
    )

    # Add current time context for Claude
    result['current_time'] = format_datetime_for_claude()

    return result


@mcp.tool()
async def get_schedule_homework() -> dict:
    """
    DEPRECATED: Use get_homework_overview() instead for better functionality.

    Get homework and notes from the schedule (skema) for the current week.

    This extracts homework and notes directly from the colored lesson boxes in the schedule.
    - Blue lessons indicate homework
    - Green lessons indicate notes/information

    Returns a dictionary with:
    - lessons: List of lessons with homework or notes
    - count: Total number of lessons with content
    """
    async with StudiePlusScraper() as scraper:
        schedule_homework = await scraper.get_schedule_homework()

        return {
            "count": len(schedule_homework),
            "lessons": schedule_homework
        }


if __name__ == "__main__":
    mcp.run()
