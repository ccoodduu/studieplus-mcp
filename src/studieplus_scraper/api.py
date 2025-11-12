"""
API Layer for StudiePlus Scraper

This layer handles business logic, data transformation, and scraper lifecycle management.
It provides a clean interface between the raw scraper and the MCP server.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .scraper import StudiePlusScraper


# ==================== CACHE ====================

class SimpleCache:
    """Simple in-memory cache with TTL (Time To Live)"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def get(self, key: str, ttl_seconds: int) -> Optional[any]:
        """Get cached value if not expired"""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        age = (datetime.now() - entry['timestamp']).total_seconds()

        if age > ttl_seconds:
            # Expired, remove from cache
            del self._cache[key]
            return None

        return entry['data']

    def set(self, key: str, data: any):
        """Store data in cache with timestamp"""
        self._cache[key] = {
            'data': data,
            'timestamp': datetime.now()
        }

    def clear(self):
        """Clear all cached data"""
        self._cache.clear()

    def invalidate(self, pattern: str):
        """Invalidate cache entries matching pattern"""
        keys_to_remove = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self._cache[key]


# Global cache instance
_cache = SimpleCache()


# Cache TTL settings (in seconds)
SCHEDULE_TTL = 300  # 5 minutes
ASSIGNMENTS_TTL = 600  # 10 minutes
LESSON_DETAILS_TTL = 300  # 5 minutes


async def get_full_schedule(week_offset: int = 0) -> dict:
    """
    Get complete weekly schedule with all lessons.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

    Returns:
        {
            "week": "46",
            "year": "2025",
            "dates": ["2025-11-10", "2025-11-11", ...],
            "lessons": [Lesson (Basic)]
        }

    Example:
        schedule = await get_full_schedule(week_offset=0)
        print(f"Week {schedule['week']}: {len(schedule['lessons'])} lessons")
    """
    cache_key = f"schedule_week_{week_offset}"

    # Check cache first
    cached = _cache.get(cache_key, SCHEDULE_TTL)
    if cached is not None:
        return cached

    # Cache miss, fetch from scraper
    async with StudiePlusScraper() as scraper:
        lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

        result = {
            "week": week_number,
            "year": year,
            "dates": dates,
            "lessons": lessons
        }

        # Store in cache
        _cache.set(cache_key, result)

        return result


async def get_homework_and_notes(
    week_offset: int = 0,
    days_ahead: int = 7,
    include_details: bool = True
) -> dict:
    """
    Get lessons with homework or notes.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)
        days_ahead: Filter by days from today (7=next week, 14=two weeks, etc.)
        include_details: Fetch full homework/notes text (if False, only returns flags)

    Returns:
        {
            "count": 5,
            "lessons": [Lesson (Basic) or (Extended) if include_details]
        }

    Example:
        homework = await get_homework_and_notes(days_ahead=7, include_details=True)
        print(f"Found {homework['count']} lessons with homework/notes")
    """
    async with StudiePlusScraper() as scraper:
        lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

        # Filter: only lessons with homework or notes
        filtered = [l for l in lessons if l['has_homework'] or l['has_note']]

        # Filter by days_ahead (from today)
        today = datetime.now().date()
        cutoff_date = today + timedelta(days=days_ahead)

        date_filtered = []
        for lesson in filtered:
            lesson_date = datetime.strptime(lesson['date'], '%Y-%m-%d').date()
            if today <= lesson_date <= cutoff_date:
                date_filtered.append(lesson)

        # If include_details is True, fetch full details for each lesson
        if include_details:
            detailed_lessons = []
            for lesson in date_filtered:
                try:
                    detail = await scraper.get_lesson_details(lesson['date'], lesson['time'])
                    detailed_lessons.append(detail)
                except Exception as e:
                    print(f"[!] Warning: Could not fetch details for {lesson['id']}: {e}")
                    # Fallback to basic lesson data
                    detailed_lessons.append(lesson)

            return {
                "count": len(detailed_lessons),
                "lessons": detailed_lessons
            }
        else:
            return {
                "count": len(date_filtered),
                "lessons": date_filtered
            }


async def get_lesson_detail(date: str, time: str) -> dict:
    """
    Get full details for a specific lesson.

    Args:
        date: ISO format (YYYY-MM-DD)
        time: Time range (HH:MM-HH:MM)

    Returns:
        Lesson (Extended) with homework, notes, and files

    Example:
        detail = await get_lesson_detail("2025-11-10", "08:15-09:15")
        print(f"Homework: {detail['homework']}")
    """
    cache_key = f"lesson_{date}_{time}"

    # Check cache first
    cached = _cache.get(cache_key, LESSON_DETAILS_TTL)
    if cached is not None:
        return cached

    # Cache miss, fetch from scraper
    async with StudiePlusScraper() as scraper:
        detail = await scraper.get_lesson_details(date=date, time=time)

        # Store in cache
        _cache.set(cache_key, detail)

        return detail


async def download_file(file_url: str, file_name: str, output_dir: str = "./downloads") -> dict:
    """
    Download a file from a lesson to the downloads folder.

    Args:
        file_url: URL of the file to download
        file_name: Name of the file
        output_dir: Directory to save the file (default: ./downloads)

    Returns:
        {
            'success': bool,
            'file_path': str,
            'file_name': str,
            'file_size': int
        }

    Example:
        result = await download_file("https://...", "rapport.pdf")
        print(f"Downloaded to: {result['file_path']}")
    """
    async with StudiePlusScraper() as scraper:
        result = await scraper.download_lesson_file(
            file_url=file_url,
            file_name=file_name,
            output_dir=output_dir
        )
        return result


async def load_file(file_url: str, file_name: str) -> dict:
    """
    Load a file from a lesson and return its content for Claude to read.

    Args:
        file_url: URL of the file to load
        file_name: Name of the file

    Returns:
        {
            'success': bool,
            'file_name': str,
            'content': str or base64,
            'content_type': str,
            'size': int,
            'is_text': bool
        }

    Example:
        result = await load_file("https://...", "rapport.pdf")
        if result['success']:
            print(f"File content: {result['content']}")
    """
    async with StudiePlusScraper() as scraper:
        result = await scraper.load_lesson_file(
            file_url=file_url,
            file_name=file_name
        )
        return result


# ==================== ASSIGNMENTS (Afleveringer) ====================

async def get_all_assignments() -> dict:
    """
    Get all assignments from the Opgaver (Assignments) page.

    Returns:
        {
            'count': int,
            'assignments': [
                {
                    'subject': str,
                    'title': str,
                    'subject_budget_hours': str,
                    'hours_spent': str,
                    'class': str,
                    'week': str,
                    'deadline': str,
                    'row_index': str
                }
            ]
        }

    Example:
        assignments = await get_all_assignments()
        print(f"Found {assignments['count']} assignments")
    """
    cache_key = "assignments_all"

    # Check cache first
    cached = _cache.get(cache_key, ASSIGNMENTS_TTL)
    if cached is not None:
        return cached

    # Cache miss, fetch from scraper
    async with StudiePlusScraper() as scraper:
        assignments = await scraper.get_homework()
        result = {
            'count': len(assignments),
            'assignments': assignments
        }

        # Store in cache
        _cache.set(cache_key, result)

        return result


async def get_upcoming_assignments(days: int = 7) -> dict:
    """
    Get assignments with deadlines within the next N days.

    Args:
        days: Number of days to look ahead (default: 7)

    Returns:
        {
            'count': int,
            'days': int,
            'assignments': [Assignment]
        }

    Example:
        upcoming = await get_upcoming_assignments(days=14)
        print(f"Found {upcoming['count']} assignments due in next 14 days")
    """
    async with StudiePlusScraper() as scraper:
        all_assignments = await scraper.get_homework()

        cutoff_date = datetime.now() + timedelta(days=days)
        upcoming = []

        for assignment in all_assignments:
            deadline_str = assignment.get('deadline', '')
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str, '%d.%m.%Y %H:%M')
                    if deadline <= cutoff_date:
                        upcoming.append(assignment)
                except:
                    pass

        return {
            'count': len(upcoming),
            'days': days,
            'assignments': upcoming
        }


async def get_assignments_by_subject(subject: str) -> dict:
    """
    Get assignments filtered by subject name.

    Args:
        subject: Subject name (e.g., "Matematik", "Dansk", "Engelsk")

    Returns:
        {
            'subject': str,
            'count': int,
            'assignments': [Assignment]
        }

    Example:
        math_assignments = await get_assignments_by_subject("Matematik")
        print(f"Found {math_assignments['count']} math assignments")
    """
    async with StudiePlusScraper() as scraper:
        all_assignments = await scraper.get_homework()

        filtered = [
            a for a in all_assignments
            if subject.lower() in a.get('subject', '').lower()
        ]

        return {
            'subject': subject,
            'count': len(filtered),
            'assignments': filtered
        }


async def get_assignment_detail(row_index: str) -> dict:
    """
    Get detailed information about a specific assignment.

    Args:
        row_index: The row index of the assignment (from 'row_index' field)

    Returns:
        {
            'assignment_title': str,
            'subject': str,
            'description': str,
            'student_time': str,
            'responsible': str,
            'course': str,
            'evaluation_form': str,
            'groups': str,
            'submission_status': str,
            'deadline': str,
            'files': [{'name': str, 'url': str}],
            'row_index': str
        }

    Example:
        details = await get_assignment_detail("5")
        print(f"Assignment: {details['assignment_title']}")
        print(f"Description: {details['description']}")
    """
    async with StudiePlusScraper() as scraper:
        details = await scraper.get_assignment_details(row_index)
        return details
