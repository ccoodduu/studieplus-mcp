"""
API Layer for StudiePlus Scraper

This layer handles business logic, data transformation, and scraper lifecycle management.
It provides a clean interface between the raw scraper and the MCP server.

Uses lightweight HTTP-based scraper by default.
Set USE_PLAYWRIGHT_SCRAPER=true to use Playwright browser automation instead.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from .scraper import StudiePlusScraper
from .requests_scraper import StudiePlusRequestsScraper
from .logger import logger


def get_scraper():
    """
    Factory function to get the appropriate scraper based on environment.

    By default uses lightweight HTTP scraper (~30MB RAM).
    Set USE_PLAYWRIGHT_SCRAPER=true to use Playwright browser automation (~300-500MB RAM).
    """
    use_playwright = os.getenv('USE_PLAYWRIGHT_SCRAPER', '').lower() in ('true', '1', 'yes')

    if use_playwright:
        logger.info("Using Playwright browser scraper")
        return StudiePlusScraper()
    else:
        logger.info("Using lightweight requests-based scraper")
        return StudiePlusRequestsScraper()


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

async def download_file(file_url: str, file_name: str, output_dir: str = None) -> dict:
    """
    Download a file from a lesson to the user's computer.

    Args:
        file_url: URL of the file to download
        file_name: Name of the file
        output_dir: Absolute path to save directory (default: user's Downloads folder)
    """
    scraper = get_scraper()
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
    async with get_scraper() as scraper:
        result = await scraper.load_lesson_file(
            file_url=file_url,
            file_name=file_name
        )
        return result


async def get_lesson_files(lesson_id: int = None, file_container_id: int = None) -> dict:
    """
    Get files attached to a lesson with download URLs.

    Args:
        lesson_id: The lesson/skema event ID (from lessons with has_files=True)
        file_container_id: Deprecated alias for lesson_id
    """
    lid = lesson_id or file_container_id
    if not lid:
        return {'count': 0, 'files': [], 'error': 'No lesson_id provided'}

    scraper = get_scraper()
    if hasattr(scraper, 'get_lesson_files_with_urls'):
        files = scraper.get_lesson_files_with_urls(lid)
        return {
            'lesson_id': lid,
            'count': len(files),
            'files': files
        }
    else:
        return {
            'lesson_id': lid,
            'count': 0,
            'files': [],
            'error': 'File API not available with Playwright scraper'
        }


# ==================== ASSIGNMENTS (Afleveringer) ====================

async def get_assignment_detail(assignment_id: str) -> dict:
    """
    Get detailed information about a specific assignment.

    Args:
        assignment_id: The assignment id (from 'id' field in get_assignments)

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
            'id': str
        }

    Example:
        details = await get_assignment_detail("5")
        print(f"Assignment: {details['assignment_title']}")
        print(f"Description: {details['description']}")
    """
    async with get_scraper() as scraper:
        details = await scraper.get_assignment_details(assignment_id)
        return details


# ==================== CONVENIENCE FUNCTIONS ====================

WEEKDAYS_DA = {
    0: "Mandag", 1: "Tirsdag", 2: "Onsdag", 3: "Torsdag",
    4: "Fredag", 5: "Lørdag", 6: "Søndag"
}


async def get_day_overview(day_offset: int = 0) -> dict:
    """
    Get complete overview for a specific day: schedule, homework, notes, and assignments due.

    Args:
        day_offset: Days from today (0=today, 1=tomorrow, -1=yesterday)

    Returns:
        {
            'date': str (ISO format),
            'weekday': str (Danish),
            'lessons': [{'time', 'subject', 'teacher', 'room', 'lesson_id'}],
            'homework': [lessons with homework text],
            'notes': [lessons with notes text],
            'assignments_due': [assignments with deadline this day],
            'first_lesson': {'time', 'room'} or None,
            'last_lesson': {'time', 'room'} or None
        }
    """
    target_date = datetime.now().date() + timedelta(days=day_offset)
    target_date_str = target_date.strftime('%Y-%m-%d')
    weekday = WEEKDAYS_DA[target_date.weekday()]

    # Calculate which week offset we need
    today = datetime.now().date()
    today_week = today.isocalendar()[1]
    target_week = target_date.isocalendar()[1]
    week_offset = target_week - today_week

    # Handle year boundary
    if target_date.year > today.year:
        week_offset = target_week + (52 - today_week)
    elif target_date.year < today.year:
        week_offset = -(today_week + (52 - target_week))

    async with get_scraper() as scraper:
        # Get schedule for the week containing target date
        lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

        # Filter lessons for target date
        day_lessons = [l for l in lessons if l.get('date') == target_date_str]
        day_lessons.sort(key=lambda x: x.get('time', ''))

        # Separate homework and notes
        homework = [l for l in day_lessons if l.get('has_homework')]
        notes = [l for l in day_lessons if l.get('has_note')]

        # Get assignments due this day
        all_assignments = await scraper.get_homework(only_open=True)
        assignments_due = []
        for a in all_assignments:
            deadline = a.get('deadline', '')
            if deadline:
                try:
                    deadline_dt = datetime.strptime(deadline, '%d.%m.%Y %H:%M')
                    if deadline_dt.date() == target_date:
                        assignments_due.append(a)
                except:
                    pass

        # Clean up lesson data for output
        clean_lessons = []
        for l in day_lessons:
            lesson_data = {
                'time': l.get('time'),
                'subject': l.get('subject'),
                'teacher': l.get('teacher'),
                'room': l.get('room'),
                'lesson_id': l.get('lesson_id'),
                'has_homework': l.get('has_homework', False),
                'has_note': l.get('has_note', False),
                'has_files': l.get('has_files', False),
                'homework': l.get('homework', ''),
                'note': l.get('note', ''),
            }
            # lesson_id is used for get_lesson_files when has_files=True
            clean_lessons.append(lesson_data)

        # First and last lesson info
        first_lesson = None
        last_lesson = None
        if clean_lessons:
            first = clean_lessons[0]
            first_lesson = {'time': first['time'], 'room': first['room'], 'subject': first['subject']}
            last = clean_lessons[-1]
            last_lesson = {'time': last['time'], 'room': last['room'], 'subject': last['subject']}

        return {
            'date': target_date_str,
            'weekday': weekday,
            'lessons': clean_lessons,
            'homework': homework,
            'notes': notes,
            'assignments_due': assignments_due,
            'first_lesson': first_lesson,
            'last_lesson': last_lesson,
        }


async def get_week_overview(week_offset: int = 0) -> dict:
    """
    Get complete overview for a specific week: schedule, homework, notes, and assignments.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

    Returns:
        {
            'week': str (e.g., "4/2026"),
            'days': [{'date', 'weekday', 'lessons': [...]}],
            'homework_count': int,
            'notes_count': int,
            'assignments': [assignments with deadline in this week]
        }
    """
    async with get_scraper() as scraper:
        lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

        # Group lessons by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for lesson in lessons:
            by_date[lesson['date']].append(lesson)

        # Build days structure
        days = []
        homework_count = 0
        notes_count = 0

        for date_str in sorted(by_date.keys()):
            date_lessons = sorted(by_date[date_str], key=lambda x: x['time'])
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            weekday = WEEKDAYS_DA[dt.weekday()]

            # Count homework and notes
            for l in date_lessons:
                if l.get('has_homework'):
                    homework_count += 1
                if l.get('has_note'):
                    notes_count += 1

            # Clean up lessons
            clean_lessons = []
            for l in date_lessons:
                lesson_data = {
                    'time': l.get('time'),
                    'subject': l.get('subject'),
                    'teacher': l.get('teacher'),
                    'room': l.get('room'),
                    'lesson_id': l.get('lesson_id'),
                    'has_homework': l.get('has_homework', False),
                    'has_note': l.get('has_note', False),
                    'has_files': l.get('has_files', False),
                    'homework': l.get('homework', ''),
                    'note': l.get('note', ''),
                }
                if l.get('file_container_id'):
                    lesson_data['file_container_id'] = l['file_container_id']
                clean_lessons.append(lesson_data)

            days.append({
                'date': date_str,
                'weekday': weekday,
                'lessons': clean_lessons,
            })

        # Get week date range for assignment filtering
        if dates:
            week_start = datetime.strptime(min(dates), '%Y-%m-%d').date()
            week_end = datetime.strptime(max(dates), '%Y-%m-%d').date()
        else:
            # Fallback: calculate from week number
            week_start = datetime.now().date() + timedelta(weeks=week_offset)
            week_start = week_start - timedelta(days=week_start.weekday())
            week_end = week_start + timedelta(days=6)

        # Get assignments due this week
        all_assignments = await scraper.get_homework(only_open=True)
        week_assignments = []
        for a in all_assignments:
            deadline = a.get('deadline', '')
            if deadline:
                try:
                    deadline_dt = datetime.strptime(deadline, '%d.%m.%Y %H:%M')
                    if week_start <= deadline_dt.date() <= week_end:
                        week_assignments.append(a)
                except:
                    pass

        return {
            'week': f"{week_number}/{year}",
            'days': days,
            'homework_count': homework_count,
            'notes_count': notes_count,
            'assignments': week_assignments,
        }


async def get_assignments_filtered(
    include_submitted: bool = False,
    days_ahead: int = None,
    subject: str = None
) -> dict:
    """
    Get assignments with optional filters.

    Args:
        include_submitted: Include already submitted assignments (default: False)
        days_ahead: Only assignments with deadline within N days (None = all)
        subject: Filter by subject name (None = all subjects)

    Returns:
        {
            'count': int,
            'filters': {'include_submitted', 'days_ahead', 'subject'},
            'assignments': [Assignment]
        }
    """
    async with get_scraper() as scraper:
        all_assignments = await scraper.get_homework(only_open=not include_submitted)

        filtered = all_assignments

        # Filter by days_ahead
        if days_ahead is not None:
            cutoff_date = datetime.now() + timedelta(days=days_ahead)
            filtered = []
            for a in all_assignments:
                deadline = a.get('deadline', '')
                if deadline:
                    try:
                        deadline_dt = datetime.strptime(deadline, '%d.%m.%Y %H:%M')
                        if deadline_dt <= cutoff_date:
                            filtered.append(a)
                    except:
                        pass

        # Filter by subject
        if subject:
            filtered = [
                a for a in filtered
                if subject.lower() in a.get('subject', '').lower()
            ]

        return {
            'count': len(filtered),
            'filters': {
                'include_submitted': include_submitted,
                'days_ahead': days_ahead,
                'subject': subject,
            },
            'assignments': filtered,
        }
