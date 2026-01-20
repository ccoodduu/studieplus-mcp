"""
API Layer for StudiePlus Scraper

This layer handles business logic, data transformation, and scraper lifecycle management.
It provides a clean interface between the raw scraper and the MCP server.

Set USE_REQUESTS_SCRAPER=true in environment to use lightweight HTTP-based scraper
instead of Playwright browser automation. Recommended for low-memory environments.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
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
LESSON_DETAILS_TTL = 300  # 5 minutes


def _group_lessons_by_date(lessons: List[Dict], week: str, year: str) -> dict:
    """
    Group lessons by date for better structure.
    Removes redundant date/weekday/id fields from lessons since they're at day level.
    """
    from collections import defaultdict

    by_date = defaultdict(list)
    for lesson in lessons:
        by_date[lesson['date']].append(lesson)

    days = []
    weekday_map = {
        0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"
    }

    for date in sorted(by_date.keys()):
        date_lessons = sorted(by_date[date], key=lambda x: x['time'])

        # Remove redundant fields from each lesson
        cleaned_lessons = []
        for lesson in date_lessons:
            cleaned = {k: v for k, v in lesson.items() if k not in ('date', 'weekday', 'id')}
            cleaned_lessons.append(cleaned)

        dt = datetime.strptime(date, '%Y-%m-%d')
        weekday = weekday_map[dt.weekday()]

        days.append({
            'date': date,
            'day': weekday,
            'lessons': cleaned_lessons
        })

    return {
        'week': f"{week}/{year}",
        'schedule': days
    }


async def get_full_schedule(week_offset: int = 0) -> dict:
    """
    Get complete weekly schedule grouped by date.

    Args:
        week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

    Returns:
        {
            "week": "48/2025",
            "schedule": [
                {"date": "2025-11-25", "day": "Mon", "lessons": [
                    {"time": "08:15-09:15", "subject": "Kemi B", "teacher": "ripe", "room": "M2500",
                     "has_homework": false, "has_note": false, "has_files": false}
                ]}
            ]
        }
    """
    cache_key = f"schedule_week_{week_offset}"

    # Check cache first
    cached = _cache.get(cache_key, SCHEDULE_TTL)
    if cached is not None:
        return cached

    # Cache miss, fetch from scraper
    async with get_scraper() as scraper:
        lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

        result = _group_lessons_by_date(lessons, week_number, year)

        # Store in cache
        _cache.set(cache_key, result)

        return result


async def get_homework_and_notes(
    days_ahead: int = 7,
    include_details: bool = True
) -> dict:
    """
    Get lessons with homework or notes.

    Automatically fetches from multiple weeks if needed to cover the days_ahead range.

    Args:
        days_ahead: Number of days to look ahead from today (default: 7)
        include_details: Fetch full homework/notes text (if False, only returns flags)

    Returns:
        {
            "count": int,
            "lessons": [Lesson (Basic) or (Extended) if include_details]
        }

    Example:
        homework = await get_homework_and_notes(days_ahead=14, include_details=True)
        print(f"Found {homework['count']} lessons with homework/notes in next 14 days")
    """
    async with get_scraper() as scraper:
        today = datetime.now().date()
        cutoff_date = today + timedelta(days=days_ahead)

        # Calculate how many weeks we need to fetch
        current_week = today.isocalendar()[1]
        target_week = cutoff_date.isocalendar()[1]
        weeks_to_fetch = target_week - current_week + 1

        all_filtered = []

        # Fetch lessons from all necessary weeks
        for week_offset in range(weeks_to_fetch):
            try:
                lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

                # Filter: only lessons with homework or notes
                filtered = [l for l in lessons if l['has_homework'] or l['has_note']]

                # Filter by date range
                for lesson in filtered:
                    lesson_date = datetime.strptime(lesson['date'], '%Y-%m-%d').date()
                    if today <= lesson_date <= cutoff_date:
                        all_filtered.append(lesson)
            except Exception as e:
                logger.warning(f"Could not fetch week {week_offset}: {e}")

        # If include_details is True, fetch full details for each lesson
        if include_details:
            detailed_lessons = []
            for lesson in all_filtered:
                try:
                    detail = await scraper.get_lesson_details(lesson['date'], lesson['time'])
                    detailed_lessons.append(detail)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {lesson['id']}: {e}")
                    # Fallback to basic lesson data
                    detailed_lessons.append(lesson)

            return {
                "count": len(detailed_lessons),
                "lessons": detailed_lessons
            }
        else:
            return {
                "count": len(all_filtered),
                "lessons": all_filtered
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
    async with get_scraper() as scraper:
        detail = await scraper.get_lesson_details(date=date, time=time)

        # Store in cache
        _cache.set(cache_key, detail)

        return detail


async def get_notes_overview(
    days_ahead: int = 7,
    include_details: bool = True
) -> dict:
    """
    Get lessons with notes.

    Automatically fetches from multiple weeks if needed to cover the days_ahead range.

    Args:
        days_ahead: Number of days to look ahead from today (default: 7)
        include_details: Fetch full notes text (if False, only returns flags)

    Returns:
        {
            "count": int,
            "lessons": [Lesson (Basic) or (Extended) if include_details]
        }

    Example:
        notes = await get_notes_overview(days_ahead=14, include_details=True)
        print(f"Found {notes['count']} lessons with notes in next 14 days")
    """
    async with get_scraper() as scraper:
        today = datetime.now().date()
        cutoff_date = today + timedelta(days=days_ahead)

        # Calculate how many weeks we need to fetch
        # Get current week number and target week number
        current_week = today.isocalendar()[1]
        target_week = cutoff_date.isocalendar()[1]
        weeks_to_fetch = target_week - current_week + 1

        all_filtered = []

        # Fetch lessons from all necessary weeks
        for week_offset in range(weeks_to_fetch):
            try:
                lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=week_offset)

                # Filter: only lessons with notes
                filtered = [l for l in lessons if l['has_note']]

                # Filter by date range
                for lesson in filtered:
                    lesson_date = datetime.strptime(lesson['date'], '%Y-%m-%d').date()
                    if today <= lesson_date <= cutoff_date:
                        all_filtered.append(lesson)
            except Exception as e:
                logger.warning(f"Could not fetch week {week_offset}: {e}")

        # If include_details is True, fetch full details for each lesson
        if include_details:
            detailed_lessons = []
            for lesson in all_filtered:
                try:
                    detail = await scraper.get_lesson_details(lesson['date'], lesson['time'])
                    detailed_lessons.append(detail)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {lesson['id']}: {e}")
                    # Fallback to basic lesson data
                    detailed_lessons.append(lesson)

            return {
                "count": len(detailed_lessons),
                "lessons": detailed_lessons
            }
        else:
            return {
                "count": len(all_filtered),
                "lessons": all_filtered
            }


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
    async with get_scraper() as scraper:
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


async def get_lesson_files(lesson_id: int) -> dict:
    """
    Get files attached to a lesson with download URLs.

    Args:
        lesson_id: The lesson ID (from the 'lesson_id' field in schedule)

    Returns:
        {
            'lesson_id': int,
            'count': int,
            'files': [
                {
                    'name': str,
                    'id': int,
                    'url': str  # Signed S3 URL, valid for ~5 minutes
                }
            ]
        }

    Example:
        files = await get_lesson_files(7620074)
        for f in files['files']:
            print(f"{f['name']}: {f['url']}")
    """
    scraper = get_scraper()
    if hasattr(scraper, 'get_lesson_files_with_urls'):
        files = scraper.get_lesson_files_with_urls(lesson_id)
        return {
            'lesson_id': lesson_id,
            'count': len(files),
            'files': files
        }
    else:
        return {
            'lesson_id': lesson_id,
            'count': 0,
            'files': [],
            'error': 'File API not available with Playwright scraper'
        }


# ==================== ASSIGNMENTS (Afleveringer) ====================

async def get_all_assignments(only_open: bool = True) -> dict:
    """
    Get all assignments from the Opgaver (Assignments) page.

    Args:
        only_open: If True, only return non-submitted/open assignments

    Returns:
        {
            'count': int,
            'only_open': bool,
            'assignments': [
                {
                    'subject': str,
                    'title': str,
                    'subject_budget_hours': str,
                    'hours_spent': str,
                    'class': str,
                    'week': str,
                    'deadline': str,
                    'submitted': bool,
                    'submission_date': str,
                    'row_index': str
                }
            ]
        }

    Example:
        assignments = await get_all_assignments()
        print(f"Found {assignments['count']} assignments")

        # Get only open assignments
        open_assignments = await get_all_assignments(only_open=True)
        print(f"Found {open_assignments['count']} open assignments")
    """
    cache_key = f"assignments_{'open' if only_open else 'all'}"

    # Check cache first
    cached = _cache.get(cache_key, ASSIGNMENTS_TTL)
    if cached is not None:
        return cached

    # Cache miss, fetch from scraper
    async with get_scraper() as scraper:
        assignments = await scraper.get_homework(only_open=only_open)
        result = {
            'count': len(assignments),
            'only_open': only_open,
            'assignments': assignments
        }

        # Store in cache
        _cache.set(cache_key, result)

        return result


async def get_open_assignments() -> dict:
    """
    Get only open (non-submitted) assignments.

    Convenience wrapper for get_all_assignments(only_open=True).

    Returns:
        {
            'count': int,
            'assignments': [Assignment]
        }

    Example:
        open_assignments = await get_open_assignments()
        print(f"Found {open_assignments['count']} open assignments")
    """
    return await get_all_assignments(only_open=True)


async def get_upcoming_assignments(days: int = 7, only_open: bool = True) -> dict:
    """
    Get assignments with deadlines within the next N days.

    Args:
        days: Number of days to look ahead (default: 7)
        only_open: If True, only return non-submitted assignments (default: False)

    Returns:
        {
            'count': int,
            'days': int,
            'only_open': bool,
            'assignments': [Assignment]
        }

    Example:
        upcoming = await get_upcoming_assignments(days=14)
        print(f"Found {upcoming['count']} assignments due in next 14 days")

        # Get only open assignments due soon
        urgent = await get_upcoming_assignments(days=7, only_open=True)
        print(f"Found {urgent['count']} open assignments due in next 7 days")
    """
    async with get_scraper() as scraper:
        all_assignments = await scraper.get_homework(only_open=only_open)

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
            'only_open': only_open,
            'assignments': upcoming
        }


async def get_assignments_by_subject(subject: str, only_open: bool = True) -> dict:
    """
    Get assignments filtered by subject name.

    Args:
        subject: Subject name (e.g., "Matematik", "Dansk", "Engelsk")
        only_open: If True, only return non-submitted assignments (default: True)

    Returns:
        {
            'subject': str,
            'count': int,
            'only_open': bool,
            'assignments': [Assignment]
        }

    Example:
        math_assignments = await get_assignments_by_subject("Matematik")
        print(f"Found {math_assignments['count']} open math assignments")
    """
    async with get_scraper() as scraper:
        all_assignments = await scraper.get_homework(only_open=only_open)

        filtered = [
            a for a in all_assignments
            if subject.lower() in a.get('subject', '').lower()
        ]

        return {
            'subject': subject,
            'count': len(filtered),
            'only_open': only_open,
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
    async with get_scraper() as scraper:
        details = await scraper.get_assignment_details(row_index)
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
            clean_lessons.append({
                'time': l.get('time'),
                'subject': l.get('subject'),
                'teacher': l.get('teacher'),
                'room': l.get('room'),
                'lesson_id': l.get('lesson_id'),
                'has_homework': l.get('has_homework', False),
                'has_note': l.get('has_note', False),
                'has_files': l.get('has_files', False),
                'homework': l.get('homework', ''),  # Homework text
                'note': l.get('note', ''),  # Note text
            })

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
                clean_lessons.append({
                    'time': l.get('time'),
                    'subject': l.get('subject'),
                    'teacher': l.get('teacher'),
                    'room': l.get('room'),
                    'lesson_id': l.get('lesson_id'),
                    'has_homework': l.get('has_homework', False),
                    'has_note': l.get('has_note', False),
                    'has_files': l.get('has_files', False),
                    'homework': l.get('homework', ''),  # Homework text
                    'note': l.get('note', ''),  # Note text
                })

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
