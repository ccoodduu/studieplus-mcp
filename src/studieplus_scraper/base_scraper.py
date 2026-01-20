"""
Base class for StudiePlus scrapers.

Defines the common interface that all scraper implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple


class BaseStudiePlusScraper(ABC):
    """
    Abstract base class for StudiePlus scrapers.

    All scraper implementations must inherit from this class
    and implement the required methods.
    """

    @abstractmethod
    async def parse_schedule(self, week_offset: int = 0) -> Tuple[List[Dict], str, str, List[str]]:
        """
        Parse schedule and return lessons.

        Args:
            week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

        Returns:
            Tuple of (lessons, week_number, year, dates)
            - lessons: List of lesson dicts with keys:
                - id, date, weekday, time, subject, teacher, room
                - has_homework, has_note, has_files
            - week_number: Week number as string
            - year: Year as string
            - dates: List of date strings for the week
        """
        pass

    @abstractmethod
    async def get_lesson_details(self, date: str, time: str) -> Dict:
        """
        Get full details for a specific lesson.

        Args:
            date: ISO format (YYYY-MM-DD)
            time: Time range (HH:MM-HH:MM)

        Returns:
            Lesson dict with extended info including homework, notes, files
        """
        pass

    @abstractmethod
    async def get_homework(self, only_open: bool = True) -> List[Dict]:
        """
        Get all assignments from the assignments page.

        Args:
            only_open: If True, only return non-submitted/open assignments

        Returns:
            List of assignment dicts with keys:
                - subject, title, deadline, class, week, submitted, etc.
        """
        pass

    @abstractmethod
    async def get_assignment_details(self, row_index: str) -> Dict:
        """
        Get detailed information about a specific assignment.

        Args:
            row_index: The row index of the assignment

        Returns:
            Assignment details dict
        """
        pass

    @abstractmethod
    async def download_lesson_file(self, file_url: str, file_name: str, output_dir: str = "./downloads") -> Dict:
        """
        Download a file from a lesson.

        Args:
            file_url: URL of the file
            file_name: Name of the file
            output_dir: Directory to save the file

        Returns:
            Dict with success status and file info
        """
        pass

    @abstractmethod
    async def load_lesson_file(self, file_url: str, file_name: str) -> Dict:
        """
        Load a file and return its content.

        Args:
            file_url: URL of the file
            file_name: Name of the file

        Returns:
            Dict with file content (text or base64)
        """
        pass

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
