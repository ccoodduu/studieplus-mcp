import asyncio
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from studieplus_scraper import api
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Studie+ Homework Checker")


# ==================== ASSIGNMENTS (Afleveringer fra Opgaver-siden) ====================

@mcp.tool()
async def get_assignments() -> dict:
    """
    Get all assignments (afleveringer) from the Opgaver page in Studie+.

    These are formal assignments with deadlines, not daily homework from schedule.

    Returns a dictionary with:
    - count: Total number of assignments
    - assignments: List of assignments with subject, title, deadline, hours, etc.
    """
    return await api.get_all_assignments()


@mcp.tool()
async def get_upcoming_assignments(days: int = 7) -> dict:
    """
    Get assignments (afleveringer) with deadlines within the next N days.

    Args:
        days: Number of days to look ahead (default: 7)

    Returns assignments due within the specified timeframe.
    """
    return await api.get_upcoming_assignments(days=days)


@mcp.tool()
async def get_assignments_by_subject(subject: str) -> dict:
    """
    Get assignments (afleveringer) for a specific subject.

    Args:
        subject: The subject name (e.g., "Matematik", "Dansk", "Engelsk")

    Returns assignments filtered by subject.
    """
    return await api.get_assignments_by_subject(subject=subject)


@mcp.tool()
async def get_assignment_details(row_index: str) -> dict:
    """
    Get detailed information about a specific assignment (aflevering).

    Args:
        row_index: The row index of the assignment (from the 'row_index' field)

    Returns detailed information including description, files, and submission status.
    """
    return await api.get_assignment_detail(row_index=row_index)



# ==================== HOMEWORK (Lektier fra skemaet) ====================

@mcp.tool()
async def get_schedule(week_offset: int = 0) -> dict:
    """
    Get complete weekly schedule with all lessons, dates, and metadata.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

    Returns a dictionary with:
    - week: Week number (e.g., "46")
    - year: Year (e.g., "2025")
    - dates: List of ISO dates for the week
    - lessons: List of all lessons with date, time, subject, teacher, room, and flags for homework/notes/files
    """
    return await api.get_full_schedule(week_offset=week_offset)


@mcp.tool()
async def get_homework_overview(week_offset: int = 0, days_ahead: int = 7) -> dict:
    """
    Get daily homework (lektier) and notes from the schedule (skema).

    This extracts homework and notes directly from the colored lesson boxes in the schedule.
    These are NOT formal assignments/afleveringer - use get_assignments() for those.

    - Blue lessons indicate homework
    - Green lessons indicate notes/information

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)
        days_ahead: How many days to look ahead from today (default: 7)

    Returns a dictionary with:
    - count: Number of lessons with homework or notes
    - lessons: List of lessons with homework/notes text (includes date, weekday, time, subject, teacher, room)
    """
    return await api.get_homework_and_notes(
        week_offset=week_offset,
        days_ahead=days_ahead,
        include_details=True
    )


@mcp.tool()
async def get_lesson_details(date: str, time: str) -> dict:
    """
    Get detailed information for a specific lesson including full homework text, notes, and files.

    Args:
        date: ISO format date (YYYY-MM-DD, e.g., "2025-11-10")
        time: Time range (HH:MM-HH:MM, e.g., "08:15-09:15")

    Returns detailed lesson information including homework text, notes, and file attachments.
    """
    return await api.get_lesson_detail(date=date, time=time)


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
    return await api.download_file(
        file_url=file_url,
        file_name=file_name,
        output_dir=output_dir
    )


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
    return await api.load_file(
        file_url=file_url,
        file_name=file_name
    )


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
