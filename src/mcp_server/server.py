import asyncio
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from studieplus_scraper.scraper import StudiePlusScraper
from studieplus_scraper import api
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Studie+ Homework Checker")


@mcp.tool()
async def get_homework() -> dict:
    """
    Get all homework assignments from Studie+ for the logged-in student.

    Returns a dictionary with:
    - assignments: List of homework assignments with subject, title, deadline, etc.
    - count: Total number of assignments
    """
    async with StudiePlusScraper() as scraper:
        homework = await scraper.get_homework()

        return {
            "count": len(homework),
            "assignments": homework
        }


@mcp.tool()
async def get_upcoming_homework(days: int = 7) -> dict:
    """
    Get homework assignments with deadlines within the next N days.

    Args:
        days: Number of days to look ahead (default: 7)

    Returns a dictionary with assignments due within the specified timeframe.
    """
    from datetime import datetime, timedelta

    async with StudiePlusScraper() as scraper:
        all_homework = await scraper.get_homework()

        cutoff_date = datetime.now() + timedelta(days=days)
        upcoming = []

        for hw in all_homework:
            deadline_str = hw.get('deadline', '')
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str, '%d.%m.%Y %H:%M')
                    if deadline <= cutoff_date:
                        upcoming.append(hw)
                except:
                    pass

        return {
            "count": len(upcoming),
            "days": days,
            "assignments": upcoming
        }


@mcp.tool()
async def get_homework_by_subject(subject: str) -> dict:
    """
    Get homework assignments for a specific subject.

    Args:
        subject: The subject name (e.g., "Matematik", "Dansk", "Engelsk")

    Returns homework assignments filtered by subject.
    """
    async with StudiePlusScraper() as scraper:
        all_homework = await scraper.get_homework()

        filtered = [hw for hw in all_homework
                   if subject.lower() in hw.get('subject', '').lower()]

        return {
            "subject": subject,
            "count": len(filtered),
            "assignments": filtered
        }


@mcp.tool()
async def get_assignment_details(row_index: str) -> dict:
    """
    Get detailed information about a specific assignment.

    Args:
        row_index: The row index of the assignment (from the 'row_index' field in homework list)

    Returns detailed information including description and files.
    """
    async with StudiePlusScraper() as scraper:
        details = await scraper.get_assignment_details(row_index)

        return details


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
    Get lessons with homework or notes from the schedule.

    This extracts homework and notes directly from the colored lesson boxes in the schedule.
    - Blue lessons indicate homework
    - Green lessons indicate notes/information

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)
        days_ahead: How many days to look ahead from today (default: 7)

    Returns a dictionary with:
    - count: Number of lessons with homework or notes
    - lessons: List of lessons with homework/notes (includes date, weekday, time, subject, teacher, room)

    Note: This is the new version of get_schedule_homework() with better date filtering and metadata.
    """
    return await api.get_homework_and_notes(
        week_offset=week_offset,
        days_ahead=days_ahead,
        include_details=False  # Set to False until get_lesson_details is implemented in scraper
    )


@mcp.tool()
async def get_lesson_details(date: str, time: str) -> dict:
    """
    Get detailed information for a specific lesson including full homework text, notes, and files.

    Args:
        date: ISO format date (YYYY-MM-DD, e.g., "2025-11-10")
        time: Time range (HH:MM-HH:MM, e.g., "08:15-09:15")

    Returns detailed lesson information including homework text, notes, and file attachments.

    Note: This function requires the scraper.get_lesson_details() method to be implemented.
    """
    return await api.get_lesson_detail(date=date, time=time)


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
