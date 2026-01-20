import os
import asyncio
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
from .logger import logger
from .base_scraper import BaseStudiePlusScraper

# Optional dependencies for Playwright scraper (not needed for lightweight requests scraper)
try:
    from playwright.async_api import async_playwright, Page, Browser
    from bs4 import BeautifulSoup
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None
    Page = None
    Browser = None
    BeautifulSoup = None

load_dotenv()

DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

def debug_path(filename: str) -> str:
    """Return path to debug file in the debug/ folder."""
    return os.path.join(DEBUG_DIR, filename)


class StudiePlusScraper(BaseStudiePlusScraper):
    """Full-featured Playwright-based scraper for StudiePlus (uses ~300MB RAM)."""

    def __init__(self, username: str = None, password: str = None, school: str = None):
        self.username = username or os.getenv("STUDIEPLUS_USERNAME")
        self.password = password or os.getenv("STUDIEPLUS_PASSWORD")
        self.school = school or os.getenv("STUDIEPLUS_SCHOOL")
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.logged_in = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright scraper requires 'playwright' and 'beautifulsoup4'. "
                "Install with: pip install playwright beautifulsoup4 && playwright install chromium"
            )
        self.playwright = await async_playwright().start()
        debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
        self.browser = await self.playwright.chromium.launch(
            headless=not debug
        )
        self.page = await self.browser.new_page()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _attempt_login(self) -> bool:
        """Single login attempt. Returns True if successful, False otherwise."""
        try:
            logger.info("Navigating to Studie+ login page...")
            await self.page.goto("https://all.studieplus.dk/")
            await self.page.wait_for_load_state("networkidle", timeout=8000)

            logger.info("Waiting for Select2 to initialize...")
            await self.page.wait_for_selector(".select2-container", timeout=10000)
            logger.info("Select2 loaded")

            logger.info("Clicking Select2 dropdown...")
            await self.page.click(".select2-container")

            logger.info(f"Looking for school: {self.school}")
            search_input = await self.page.wait_for_selector(".select2-search input, .select2-input", timeout=5000)
            await search_input.type(self.school)

            result = await self.page.wait_for_selector(f".select2-results .select2-result:has-text('{self.school}')", timeout=5000)
            await result.click()
            logger.info(f"Selected school: {self.school}")

            await self.page.screenshot(path=debug_path("before_login_button.png"))
            logger.debug("Screenshot saved")

            direkte_button = await self.page.wait_for_selector("button#direkte, button[name='how'][value='DIREKTE']", timeout=5000)
            await direkte_button.click()
            logger.info("Clicked 'Direkte' login button")

            logger.info("Waiting for login fields...")
            username_field = None
            possible_selectors = [
                "input[name='user']",
                "input[name='username']",
                "input[name='brugernavn']",
                "input[id='username']",
                "input[id='brugernavn']",
                "input[type='text']:visible"
            ]

            for selector in possible_selectors:
                try:
                    username_field = await self.page.wait_for_selector(selector, timeout=8000)
                    if username_field:
                        logger.debug(f"Found username field with selector: {selector}")
                        break
                except:
                    continue

            await self.page.screenshot(path=debug_path("after_direkte_click.png"))
            logger.debug(f"Screenshot saved to {debug_path('after_direkte_click.png')}")

            if not username_field:
                raise Exception("Could not find username field")

            await username_field.fill(self.username)
            logger.info(f"Filled username: {self.username}")

            password_field = await self.page.wait_for_selector("input[name='password'], input[name='kodeord'], input[type='password']", timeout=5000)
            await password_field.fill(self.password)
            logger.info("Filled password")

            submit_button = await self.page.wait_for_selector("button[type='submit'], input[type='submit'], button:has-text('Log ind'), button:has-text('Login')", timeout=5000)
            await submit_button.click()
            logger.info("Clicked submit button")

            # Wait for URL to change (login complete) then immediately navigate to schedule
            await self.page.wait_for_url("**/skema/**", timeout=10000)
            logger.info("Login successful!")

            # Navigate to schedule page immediately (don't wait for current page to finish)
            logger.info("Navigating to schedule page...")
            await self.page.goto("https://all.studieplus.dk/skema/")
            logger.info("Now on schedule page")

            self.logged_in = True
            return True

        except Exception as e:
            logger.error(f"Login attempt error: {e}")
            try:
                await self.page.screenshot(path=debug_path("error_page.png"))
                logger.debug(f"Error screenshot saved to {debug_path('error_page.png')}")
            except:
                pass
            return False

    async def login(self) -> bool:
        """Login with automatic retry (max 3 attempts)."""
        if self.logged_in:
            logger.info("Already logged in, skipping login")
            return True

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Login attempt {attempt}/{max_attempts}")

            success = await self._attempt_login()

            if success:
                return True

            if attempt < max_attempts:
                logger.warning(f"Login attempt {attempt} failed, retrying...")
                await asyncio.sleep(1)
            else:
                logger.error(f"All {max_attempts} login attempts failed")
                return False

        return False

    async def get_homework(self, only_open: bool = True) -> List[Dict]:
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        logger.info("Navigating to assignments page...")

        try:
            await self.page.goto("https://all.studieplus.dk/opgave/")
            await self.page.wait_for_load_state("networkidle")
            logger.info("On assignments page")

            await self.page.screenshot(path=debug_path("assignments_page.png"))
            logger.debug(f"Screenshot saved to {debug_path('assignments_page.png')}")

            homework_data = await self._extract_homework_from_page()

            if homework_data:
                # Filter by only_open if requested
                if only_open:
                    homework_data = [h for h in homework_data if not h.get('submitted', False)]
                return homework_data

            logger.info("Extracting all visible text from assignments page...")
            visible_text = await self.page.evaluate("""() => {
                return document.body.innerText;
            }""")

            with open(debug_path("assignments_text.txt"), "w", encoding="utf-8") as f:
                f.write(visible_text)
            logger.debug(f"Saved assignments page text to {debug_path('assignments_text.txt')}")

            content = await self.page.content()
            with open(debug_path("assignments_page.html"), "w", encoding="utf-8") as f:
                f.write(content)
            logger.debug(f"Saved assignments HTML to {debug_path('assignments_page.html')}")

            return []

        except Exception as e:
            logger.error(f"Error accessing assignments: {e}")

            await self.page.screenshot(path=debug_path("error_assignments.png"))
            logger.debug(f"Error screenshot saved to {debug_path('error_assignments.png')}")

            return []

    async def _extract_homework_from_page(self) -> List[Dict]:
        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        with open(debug_path("assignments_page.html"), "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug(f"Saved assignments HTML to {debug_path('assignments_page.html')}")

        homework_items = []

        assignment_table = soup.find('table') or soup.find('tbody')

        if assignment_table:
            rows = assignment_table.find_all('tr')

            for row_idx, row in enumerate(rows):
                cols = row.find_all('td')

                if len(cols) >= 6:
                    subject = cols[0].get_text(strip=True) if len(cols) > 0 else ""
                    title = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                    pulje = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                    brugt = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    class_name = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                    week = cols[5].get_text(strip=True) if len(cols) > 5 else ""
                    deadline = cols[6].get_text(strip=True) if len(cols) > 6 else ""

                    row_number = row.get('__gwt_row')

                    if subject and title:
                        homework_items.append({
                            'subject': subject,
                            'title': title,
                            'subject_budget_hours': pulje,
                            'hours_spent': brugt,
                            'class': class_name,
                            'week': week,
                            'deadline': deadline,
                            'row_index': row_number if row_number else str(row_idx)
                        })

        if homework_items:
            logger.info(f"Found {len(homework_items)} homework assignments")
            return homework_items

        return []

    async def get_assignment_details(self, row_index: str) -> Dict:
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        logger.info(f"Fetching assignment details for row {row_index}")

        try:
            logger.info("Navigating to assignments page...")
            await self.page.goto("https://all.studieplus.dk/opgave/")

            # Wait for table to load
            await self.page.wait_for_selector('tr[__gwt_row]', timeout=15000)
            logger.info("Table loaded")

            # Debug: save HTML after table load
            if os.getenv('DEBUG'):
                content = await self.page.content()
                with open(debug_path("assignment_details_page.html"), "w", encoding="utf-8") as f:
                    f.write(content)
                await self.page.screenshot(path=debug_path("assignment_details_page.png"))
                logger.debug("Saved HTML and screenshot")

            logger.info(f"Looking for 'Details' button in row {row_index}")
            details_button = await self.page.wait_for_selector(
                f'tr[__gwt_row="{row_index}"] button:has-text("Details")',
                timeout=10000
            )

            if details_button:
                await details_button.click()
                logger.info("Clicked 'Detaljer' button")

                # Wait for details dialog to appear
                await self.page.wait_for_load_state("networkidle")

                iframe_description = ""
                try:
                    iframe_locator = self.page.frame_locator('iframe.gwt-RichTextArea')
                    iframe_body = iframe_locator.locator('body')
                    iframe_description = await iframe_body.inner_text(timeout=3000)
                    logger.debug(f"Got description from iframe: {iframe_description[:100]}...")
                except Exception as e:
                    logger.debug(f"No iframe description found: {e}")

                content = await self.page.content()
                soup = BeautifulSoup(content, 'html.parser')

                result = {
                    'description': '',
                    'assignment_title': '',
                    'subject': '',
                    'student_time': '',
                    'responsible': '',
                    'course': '',
                    'evaluation_form': '',
                    'groups': '',
                    'submission_status': '',
                    'deadline': '',
                    'files': [],
                    'row_index': row_index
                }

                # Parse table rows - handle both Danish and English labels
                table_rows = soup.find_all('tr')
                for row in table_rows:
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)

                        if 'opgavetitel' in label or 'assignment title' in label:
                            result['assignment_title'] = value
                        elif 'fag/hold' in label or 'subject' in label:
                            result['subject'] = value
                        elif 'fordybelsestid' in label or 'student time' in label:
                            result['student_time'] = value
                        elif 'ansvarlig' in label or 'responsible' in label:
                            result['responsible'] = value
                        elif 'forløb' in label or 'course' in label:
                            result['course'] = value
                        elif 'bedømmelsesform' in label or 'evaluation' in label:
                            result['evaluation_form'] = value
                        elif 'grupper' in label or 'groups' in label:
                            result['groups'] = value

                # Parse submission status - handle both Danish and English
                status_divs = soup.find_all('div', class_='gwt-Label')
                for div in status_divs:
                    text = div.get_text(strip=True).lower()
                    if 'afleveringsstatus' in text or 'submission status' in text:
                        next_elem = div.find_next('h3')
                        if next_elem:
                            result['submission_status'] = next_elem.get_text(strip=True)
                    elif 'afleveringsfrist' in text or 'submission deadline' in text:
                        next_elem = div.find_next('div', class_='gwt-Label')
                        if next_elem and ':' in next_elem.get_text():
                            result['deadline'] = next_elem.get_text(strip=True)

                if iframe_description and len(iframe_description.strip()) > 0:
                    result['description'] = iframe_description.strip()
                else:
                    desc_headers = soup.find_all('h4')
                    description_parts = []
                    for header in desc_headers:
                        header_text = header.get_text(strip=True).lower()
                        # Handle both Danish and English
                        if 'opgaveformulering' in header_text or 'assignment description' in header_text:
                            next_sibling = header.find_next_sibling()
                            if next_sibling:
                                desc_text = next_sibling.get_text(strip=True)
                                no_files_texts = ['ingen filer', 'no files']
                                if desc_text and not any(nf in desc_text.lower() for nf in no_files_texts) and len(desc_text) > 5:
                                    description_parts.append(desc_text)

                    if description_parts:
                        result['description'] = '\n\n'.join(description_parts)

                # Extract files - look for anchor elements with file names in title or text
                file_anchors = soup.find_all('a', class_='gwt-Anchor')
                for link in file_anchors:
                    # Get file name from title attribute or text
                    file_name = link.get('title', '') or link.get_text(strip=True)
                    href = link.get('href', '')

                    # Check if it's a file (has file extension)
                    file_extensions = ('.pdf', '.docx', '.xlsx', '.pptx', '.zip', '.doc', '.txt', '.jpg', '.png', '.gif')
                    if file_name and any(file_name.lower().endswith(ext) for ext in file_extensions):
                        result['files'].append({
                            'name': file_name,
                            'url': href if href and not href.startswith('javascript:') else ''
                        })

                # Also check for traditional file links with href
                file_links = soup.find_all('a', href=True)
                for link in file_links:
                    href = link.get('href', '')
                    link_text = link.get_text(strip=True)
                    if (('/filer/' in href or '/bilag/' in href or '/files/' in href) and
                        link_text and len(link_text) > 2):
                        # Avoid duplicates
                        if not any(f['name'] == link_text for f in result['files']):
                            result['files'].append({
                                'name': link_text,
                                'url': href
                            })

                await self.page.screenshot(path=debug_path("assignment_details.png"))
                logger.debug(f"Screenshot saved to {debug_path('assignment_details.png')}")

                with open(debug_path("assignment_details.html"), "w", encoding="utf-8") as f:
                    f.write(content)
                logger.debug(f"Saved assignment HTML to {debug_path('assignment_details.html')}")

                return result

        except Exception as e:
            logger.error(f"Error fetching assignment details: {e}")
            import traceback
            traceback.print_exc()
            return {
                'description': '',
                'assignment_title': '',
                'subject': '',
                'student_time': '',
                'responsible': '',
                'course': '',
                'evaluation_form': '',
                'groups': '',
                'submission_status': '',
                'deadline': '',
                'files': [],
                'row_index': row_index,
                'error': str(e)
            }

    async def get_schedule_homework(self) -> List[Dict]:
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        logger.info("Parsing schedule homework from SVG...")

        # Wait for SVG to load
        await self.page.wait_for_selector('svg g.CAHE1CD-h-b', timeout=10000)

        # Get HTML content
        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Find all lesson SVG groups
        lesson_groups = soup.find_all('g', class_='CAHE1CD-h-b')
        logger.info(f"Found {len(lesson_groups)} lessons in schedule")

        homework_list = []

        for lesson in lesson_groups:
            # Get color from rect element
            rect = lesson.find('rect')
            if not rect:
                continue

            fill_color = rect.get('style', '')
            color_match = re.search(r'fill:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\)', fill_color)

            if not color_match:
                continue

            r, g, b = map(int, color_match.groups())

            # Extract lesson info from text elements
            texts = lesson.find_all('text')

            time = ""
            subject = ""
            room = ""
            teacher = ""

            for text_elem in texts:
                text_content = text_elem.get_text(strip=True)

                # Time pattern: HH:MM-HH:MM
                if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', text_content):
                    time = text_content

                # Subject (bold text after time)
                if text_elem.get('style', '') and 'font-weight: bold' in text_elem.get('style'):
                    if ':' not in text_content:  # Not the time
                        subject = text_content

                # Room and teacher (simplified detection)
                if len(text_content) > 2 and len(text_content) < 20:
                    if text_content.startswith('M') or text_content.startswith('N'):
                        room = text_content
                    elif text_content.islower() and len(text_content) < 10 and text_content.isalpha():
                        teacher = text_content

            # Check for homework or notes in title
            homework_text = ""
            note_text = ""

            for text_elem in texts:
                title_elem = text_elem.find('title')
                if title_elem:
                    title_content = title_elem.get_text(strip=True)

                    # Check if it's homework (both Danish and English)
                    if '*** Lektier ***' in title_content:
                        homework_text = title_content.replace('*** Lektier ***', '').strip()
                    elif '*** Homework ***' in title_content:
                        homework_text = title_content.replace('*** Homework ***', '').strip()

                    # Check if it's notes (both Danish and English)
                    if '*** Noter ***' in title_content:
                        note_text = title_content.replace('*** Noter ***', '').strip()
                    elif '*** Notes ***' in title_content:
                        note_text = title_content.replace('*** Notes ***', '').strip()

            # Determine lesson type by color
            lesson_type = "normal"
            if r < 150 and g > 200 and b > 200:  # Blue-ish
                lesson_type = "homework"
            elif r < 200 and g > 200 and b < 200:  # Green-ish
                lesson_type = "note"

            # Only save if there's homework or notes
            if homework_text or note_text:
                homework_list.append({
                    'time': time,
                    'subject': subject,
                    'teacher': teacher,
                    'room': room,
                    'color': f'rgb({r}, {g}, {b})',
                    'type': lesson_type,
                    'homework': homework_text,
                    'note': note_text
                })

        logger.info(f"Found {len(homework_list)} lessons with homework/notes")
        return homework_list

    def parse_week_dates(self, soup: BeautifulSoup) -> tuple[List[str], str, str]:
        """
        Extract dates, week number, and year from schedule HTML.
        Supports both Danish and English language settings.

        Args:
            soup: BeautifulSoup object of schedule page

        Returns:
            Tuple of (dates_list, week_number, year)
            - dates_list: List of 7 ISO dates ["2025-11-10", ...]
            - week_number: Week number as string ("46")
            - year: Year as string ("2025")
        """
        # Support both Danish and English weekday abbreviations
        weekdays_da = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]
        weekdays_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekdays = weekdays_da + weekdays_en
        dates = []

        # Find week info from buttons (supports both "Uge X - YYYY" and "Week X - YYYY")
        week_info = None
        buttons = soup.find_all('button')
        for btn in buttons:
            text = btn.get_text(strip=True)
            if ("Uge" in text or "Week" in text) and "-" in text:
                week_info = text
                break

        # Fallback to labels (old format)
        if not week_info:
            date_labels = soup.find_all('div', class_='gwt-Label')
            for label in date_labels:
                text = label.get_text(strip=True)
                if ("Uge" in text or "Week" in text) and "-" in text:
                    week_info = text
                    break

        if not week_info:
            raise Exception("Could not find week information in schedule")

        # Match both "Uge X - YYYY" and "Week X - YYYY"
        week_match = re.search(r'(?:Uge|Week)\s*(\d+)\s*-\s*(\d{4})', week_info)
        if not week_match:
            raise Exception(f"Could not parse week info: {week_info}")

        week_number = week_match.group(1)
        year = week_match.group(2)

        # Find dates from gwt-Label divs
        date_labels = soup.find_all('div', class_='gwt-Label')

        for label in date_labels:
            text = label.get_text(strip=True)
            for weekday in weekdays:
                if text.startswith(weekday):
                    date_match = re.search(r'(\d{1,2})/(\d{1,2})', text)
                    if date_match:
                        day = date_match.group(1).zfill(2)
                        month = date_match.group(2).zfill(2)
                        iso_date = f"{year}-{month}-{day}"
                        dates.append(iso_date)
                        break

        if len(dates) != 7:
            raise Exception(f"Expected 7 dates, found {len(dates)}")

        return (dates, week_number, year)

    def calculate_lesson_date(self, transform: str, week_dates: List[str], column_width: int = 138) -> tuple[str, str]:
        """
        Calculate lesson date and weekday from SVG transform position.

        Args:
            transform: SVG transform attribute (e.g., "translate(138, 600) rotate(0)")
            week_dates: List of 7 ISO dates for the week
            column_width: Width of each day column in pixels (default 138 for 7-day view)

        Returns:
            Tuple of (iso_date, weekday_name)
        """
        weekday_names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

        match = re.search(r'translate\((\d+),\s*(\d+)\)', transform)
        if not match:
            return (week_dates[0], weekday_names[0])

        x_pos = int(match.group(1))

        day_index = x_pos // column_width

        if day_index >= len(week_dates):
            day_index = len(week_dates) - 1

        return (week_dates[day_index], weekday_names[day_index])

    async def navigate_to_week(self, week_offset: int):
        """
        Navigate to a specific week offset from current.

        Args:
            week_offset: Number of weeks from current (positive=future, negative=past)
        """
        if week_offset == 0:
            return

        if week_offset > 0:
            button_selector = 'button:has(i.icon-chevron-right)'
            clicks = week_offset
        else:
            button_selector = 'button:has(i.icon-chevron-left)'
            clicks = abs(week_offset)

        for _ in range(clicks):
            try:
                await self.page.click(button_selector)
                await self.page.wait_for_load_state('networkidle', timeout=3000)
            except Exception as e:
                logger.warning(f"Could not navigate week: {e}")
                break

    async def parse_schedule(self, week_offset: int = 0) -> tuple[List[Dict], str, str, List[str]]:
        """
        Parse the entire weekly schedule and return ALL lessons with metadata.

        Args:
            week_offset: Weeks from current (0=this week, 1=next week, -1=last week)

        Returns:
            Tuple of (lessons, week_number, year, dates)
            - lessons: List of lesson dicts (Basic format with date, weekday, etc.)
            - week_number: Week number as string
            - year: Year as string
            - dates: List of 7 ISO dates
        """
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        await self.navigate_to_week(week_offset)

        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
        if debug:
            with open(debug_path("schedule_page.html"), "w", encoding="utf-8") as f:
                f.write(content)
            logger.debug(f"Saved schedule HTML to {debug_path('schedule_page.html')}")

        week_dates, week_number, year = self.parse_week_dates(soup)

        if debug:
            logger.debug(f"Parsed week dates: {week_dates}")
            logger.debug(f"Week {week_number}, Year {year}")

        # Find day containers (one per weekday)
        day_containers = soup.find_all('g', class_='DagMedBrikker')
        logger.info(f"Found {len(day_containers)} day containers")

        # Calculate column width dynamically by collecting all x positions
        x_positions = []
        for day_container in day_containers:
            container_transform = day_container.get('transform', '')
            match = re.search(r'translate\((\d+),\s*(\d+)\)', container_transform)
            if match:
                x_positions.append(int(match.group(1)))

        x_positions = sorted(set(x_positions))

        # Calculate column width from x positions (difference between consecutive unique positions)
        if len(x_positions) >= 2:
            column_width = x_positions[1] - x_positions[0]
        else:
            column_width = 138  # Default for 7-day view

        if debug:
            logger.debug(f"X positions: {x_positions}")
            logger.debug(f"Calculated column width: {column_width}px")

        lessons = []
        weekday_names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

        for day_container in day_containers:
            # Get day from container's transform
            container_transform = day_container.get('transform', '')
            if not container_transform:
                continue

            # Calculate which day this container represents
            match = re.search(r'translate\((\d+),\s*(\d+)\)', container_transform)
            if not match:
                continue

            x_pos = int(match.group(1))
            day_index = x_pos // column_width  # Dynamic column width

            if debug:
                logger.debug(f"Day container: x_pos={x_pos}, day_index={day_index}, weekday={weekday_names[day_index] if day_index < len(weekday_names) else 'Unknown'}")

            if day_index >= len(week_dates):
                continue

            lesson_date = week_dates[day_index]
            if debug:
                logger.debug(f"Assigned date: {lesson_date}")
            weekday = weekday_names[day_index] if day_index < len(weekday_names) else "Unknown"

            # Find all lessons in this day container
            lesson_groups = day_container.find_all('g', class_='CAHE1CD-h-b')

            for lesson in lesson_groups:
                rect = lesson.find('rect')
                if not rect:
                    continue

                fill_color = rect.get('style', '')
                color_match = re.search(r'fill:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\)', fill_color)

                if not color_match:
                    continue

                r, g, b = map(int, color_match.groups())

                texts = lesson.find_all('text')

                time = ""
                subject = ""
                room = ""
                teacher = ""

                for text_elem in texts:
                    # Get only direct text content, excluding nested <title> (tooltips)
                    # Use .string or .strings to get only direct text, not child elements
                    direct_text = ''.join(text_elem.find_all(string=True, recursive=False)).strip()
                    text_content = direct_text if direct_text else ""

                    if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', text_content):
                        time = text_content

                    # Subject is bold text with font-size 12px (not the time which is 10px)
                    style = text_elem.get('style', '')
                    if 'font-weight: bold' in style and 'font-size: 12px' in style:
                        if ':' not in text_content and len(text_content) > 1:
                            subject = text_content

                    if len(text_content) > 2 and len(text_content) < 20:
                        if text_content.startswith('M') or text_content.startswith('N'):
                            room = text_content
                        elif text_content.islower() and len(text_content) < 10 and text_content.isalpha():
                            teacher = text_content

                has_homework = False
                has_note = False
                has_files = False

                for text_elem in texts:
                    title_elem = text_elem.find('title')
                    if title_elem:
                        title_content = title_elem.get_text(strip=True)

                        # Check for homework - only if there's actual content after the header
                        if '*** Lektier ***' in title_content or '*** Homework ***' in title_content:
                            # Check if there's text after the header (more than just the header itself)
                            content_after_header = title_content.replace('*** Lektier ***', '').replace('*** Homework ***', '').strip()
                            if content_after_header and len(content_after_header) > 0:
                                has_homework = True

                        # Check for notes - only if there's actual content after the header
                        if '*** Noter ***' in title_content or '*** Notes ***' in title_content:
                            # Check if there's text after the header (more than just the header itself)
                            content_after_header = title_content.replace('*** Noter ***', '').replace('*** Notes ***', '').strip()
                            if content_after_header and len(content_after_header) > 0:
                                has_note = True

                        # Files indicator usually doesn't have content, just the marker
                        if '*** Har filer ***' in title_content or '*** Has files ***' in title_content:
                            has_files = True

                if not time or not subject:
                    continue

                lesson_id = f"{lesson_date}_{time.split('-')[0]}"

                lessons.append({
                    'id': lesson_id,
                    'date': lesson_date,
                    'weekday': weekday,
                    'time': time,
                    'subject': subject,
                    'teacher': teacher,
                    'room': room,
                    'has_homework': has_homework,
                    'has_note': has_note,
                    'has_files': has_files
                })

        logger.info(f"Parsed {len(lessons)} valid lessons")
        return (lessons, week_number, year, week_dates)

    async def get_lesson_details(self, date: str, time: str) -> Dict:
        """
        Get homework, notes, and files for a specific lesson.

        Args:
            date: ISO format (YYYY-MM-DD)
            time: Time range (HH:MM-HH:MM)

        Returns:
            Lesson Details (Extended format) with full homework/notes text and files
        """
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        target_date = datetime.strptime(date, '%Y-%m-%d').date()
        today = datetime.now().date()

        # Calculate week offset more accurately using ISO week numbers
        target_week = target_date.isocalendar()[1]
        current_week = today.isocalendar()[1]
        week_offset = target_week - current_week

        await self.navigate_to_week(week_offset)

        # Wait for SVG schedule to load before parsing
        await self.page.wait_for_selector('svg g.CAHE1CD-h-b', timeout=10000)

        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        week_dates, week_number, year = self.parse_week_dates(soup)

        # Calculate column width dynamically from day containers
        day_containers = soup.find_all('g', class_='DagMedBrikker')
        x_positions = []
        for day_container in day_containers:
            container_transform = day_container.get('transform', '')
            match = re.search(r'translate\((\d+),\s*(\d+)\)', container_transform)
            if match:
                x_positions.append(int(match.group(1)))
        x_positions = sorted(set(x_positions))
        column_width = x_positions[1] - x_positions[0] if len(x_positions) >= 2 else 138

        weekday_names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

        if os.getenv('DEBUG'):
            logger.debug(f"Looking for lesson at date={date} time={time}")
            logger.debug(f"Week dates from schedule: {week_dates}")
            logger.debug(f"Found {len(day_containers)} day containers")

        target_lesson = None

        # Iterate through day containers (same approach as parse_schedule)
        for day_container in day_containers:
            container_transform = day_container.get('transform', '')
            if not container_transform:
                continue

            match = re.search(r'translate\((\d+),\s*(\d+)\)', container_transform)
            if not match:
                continue

            x_pos = int(match.group(1))
            day_index = x_pos // column_width

            if day_index >= len(week_dates):
                continue

            lesson_date = week_dates[day_index]
            weekday = weekday_names[day_index] if day_index < len(weekday_names) else "Unknown"

            # Skip if this isn't the target date
            if lesson_date != date:
                continue

            if os.getenv('DEBUG'):
                logger.debug(f"Found day container for target date: {lesson_date}")

            # Find lessons within this day container
            lesson_groups = day_container.find_all('g', class_='CAHE1CD-h-b')

            for lesson in lesson_groups:
                texts = lesson.find_all('text')
                lesson_time = ""

                for text_elem in texts:
                    # Get only direct text content, excluding nested <title> (tooltips)
                    direct_text = ''.join(text_elem.find_all(string=True, recursive=False)).strip()
                    text_content = direct_text if direct_text else ""
                    if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', text_content):
                        lesson_time = text_content
                        break

                if os.getenv('DEBUG'):
                    logger.debug(f"Found lesson with time: {lesson_time}")

                if lesson_time == time:
                    target_lesson = lesson
                    break

            if target_lesson:
                break

        if not target_lesson:
            raise Exception(f"Could not find lesson at {date} {time}")

        rect = target_lesson.find('rect')
        if not rect:
            raise Exception("Lesson has no rect element")

        fill_color = rect.get('style', '')
        color_match = re.search(r'fill:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\)', fill_color)

        if not color_match:
            raise Exception("Could not extract lesson color")

        r, g, b = map(int, color_match.groups())

        texts = target_lesson.find_all('text')

        subject = ""
        teacher = ""
        room = ""
        homework_text = ""
        note_text = ""
        has_files = False

        for text_elem in texts:
            # Get only direct text content, excluding nested <title> (tooltips)
            direct_text = ''.join(text_elem.find_all(string=True, recursive=False)).strip()
            text_content = direct_text if direct_text else ""

            style = text_elem.get('style', '')

            # Subject is bold text with font-size 12px (not 13px which is the absence marker)
            if 'font-weight: bold' in style and 'font-size: 12px' in style:
                if ':' not in text_content and len(text_content) > 1:
                    subject = text_content

            if len(text_content) > 2 and len(text_content) < 20:
                if text_content.startswith('M') or text_content.startswith('N'):
                    room = text_content
                elif text_content.islower() and len(text_content) < 10 and text_content.isalpha():
                    teacher = text_content

            title_elem = text_elem.find('title')
            if title_elem:
                title_content = title_elem.get_text(strip=True)

                if '*** Lektier ***' in title_content:
                    homework_text = title_content.replace('*** Lektier ***', '').strip()
                elif '*** Homework ***' in title_content:
                    homework_text = title_content.replace('*** Homework ***', '').strip()

                if '*** Noter ***' in title_content:
                    note_text = title_content.replace('*** Noter ***', '').strip()
                elif '*** Notes ***' in title_content:
                    note_text = title_content.replace('*** Notes ***', '').strip()

                if '*** Har filer ***' in title_content or '*** Has files ***' in title_content:
                    has_files = True

        lesson_id = f"{date}_{time.split('-')[0]}"

        files = []
        popup_homework = ""
        popup_note = ""

        # Always try to open popup to get full details (better formatting, links, files)
        try:
            # Get the lesson's position within the day container
            lesson_transform = target_lesson.get('transform', '')
            lesson_match = re.search(r'translate\((\d+),\s*(\d+)\)', lesson_transform)

            if lesson_match:
                lesson_local_x, lesson_y = int(lesson_match.group(1)), int(lesson_match.group(2))
                day_container_x = day_index * column_width

                if os.getenv('DEBUG'):
                    logger.debug(f"Target lesson at day_x={day_container_x}, y={lesson_y}")

                # Find SVG and scroll into view
                svg_elem = await self.page.query_selector('svg[viewBox]')
                if svg_elem:
                    await svg_elem.scroll_into_view_if_needed()

                    svg_box = await svg_elem.bounding_box()
                    if svg_box:
                        # Calculate click position: SVG position + day container x + lesson offset
                        click_x = svg_box['x'] + day_container_x + lesson_local_x + 50
                        click_y = svg_box['y'] + lesson_y + 20

                        if os.getenv('DEBUG'):
                            logger.debug(f"SVG box: ({svg_box['x']:.0f}, {svg_box['y']:.0f})")
                            logger.debug(f"Clicking on lesson at ({click_x:.0f}, {click_y:.0f})")

                        await self.page.mouse.click(click_x, click_y)

                        # Press Ctrl+Alt+N to open the note/homework popup
                        if os.getenv('DEBUG'):
                            logger.debug("Pressing Ctrl+Alt+N to open popup...")
                        await self.page.keyboard.press('Control+Alt+n')

                        # Wait for popup to appear
                        await self.page.wait_for_selector('.udialog', state='attached', timeout=5000)

                        # Take screenshot for debugging
                        if os.getenv('DEBUG'):
                            debug_screenshot = os.path.join(os.path.dirname(__file__), '..', '..', 'debug', 'after_ctrl_alt_n.png')
                            await self.page.screenshot(path=debug_screenshot)
                            logger.debug(f"Screenshot saved to {debug_screenshot}")

                        # Extract popup content
                        try:

                            if os.getenv('DEBUG'):
                                logger.debug("Extracting popup content...")

                            popup_content = await self.page.content()
                            popup_soup = BeautifulSoup(popup_content, 'html.parser')

                            # Save popup HTML for debugging
                            if os.getenv('DEBUG'):
                                debug_html = os.path.join(os.path.dirname(__file__), '..', '..', 'debug', 'lesson_popup.html')
                                with open(debug_html, 'w', encoding='utf-8') as f:
                                    f.write(popup_content)
                                logger.debug(f"Saved popup HTML to {debug_html}")

                            # Find the dialog box - StudiePlus uses "udialog" class
                            dialog = (
                                popup_soup.find('div', class_='udialog') or
                                popup_soup.find('div', class_='gwt-DialogBox') or
                                popup_soup.find('div', class_='gwt-PopupPanel')
                            )

                            if os.getenv('DEBUG'):
                                logger.debug(f"Dialog found: {bool(dialog)}")

                            if dialog:
                                # StudiePlus popup uses control-group divs with control-label and controls
                                control_groups = dialog.find_all('div', class_='control-group')

                                for group in control_groups:
                                    label_elem = group.find('label', class_='control-label')
                                    controls_elem = group.find('div', class_='controls')

                                    if label_elem and controls_elem:
                                        label_text = label_elem.get_text(strip=True).lower()

                                        if 'homework' in label_text or 'lektier' in label_text:
                                            popup_homework = controls_elem.get_text(separator=' ', strip=True)
                                            # Clean up any escaped HTML tags in the text
                                            popup_homework = re.sub(r'<[^>]+>', '', popup_homework)
                                            popup_homework = re.sub(r'\s+', ' ', popup_homework).strip()

                                            if os.getenv('DEBUG'):
                                                logger.debug(f"Found homework: {popup_homework[:100]}...")

                                        elif label_text == 'note' or label_text == 'noter':
                                            popup_note = controls_elem.get_text(separator=' ', strip=True)
                                            # Clean up any escaped HTML tags in the text
                                            popup_note = re.sub(r'<[^>]+>', '', popup_note)
                                            popup_note = re.sub(r'\s+', ' ', popup_note).strip()

                                            if os.getenv('DEBUG'):
                                                logger.debug(f"Found note: {popup_note[:100] if popup_note else 'empty'}...")

                                        elif 'filer' in label_text or 'files' in label_text:
                                            file_links = controls_elem.find_all('a', href=True)
                                            for link in file_links:
                                                href = link.get('href', '')
                                                file_name = link.get_text(strip=True)
                                                if file_name and href and not href.startswith('javascript:'):
                                                    full_url = href if href.startswith('http') else f"https://all.studieplus.dk{href}"
                                                    files.append({
                                                        'name': file_name,
                                                        'url': full_url
                                                    })
                                            if os.getenv('DEBUG'):
                                                logger.debug(f"Found {len(files)} files")

                            # Extract URLs from links by clicking them and capturing navigation
                            extracted_links = []
                            try:
                                # Use locator for more robust element handling
                                link_locator = self.page.locator('.udialog a.gwt-Anchor')
                                link_count = await link_locator.count()

                                if os.getenv('DEBUG'):
                                    logger.debug(f"Found {link_count} link elements in popup")

                                for i in range(link_count):
                                    try:
                                        # Get fresh reference to the nth link
                                        link = link_locator.nth(i)
                                        link_text = await link.inner_text()
                                        link_text = re.sub(r'<[^>]+>', '', link_text).strip()

                                        if not link_text or len(link_text) < 3:
                                            continue

                                        if os.getenv('DEBUG'):
                                            logger.debug(f"Clicking link {i}: '{link_text}'")

                                        # Try to capture new page (popup window)
                                        try:
                                            async with self.page.context.expect_page(timeout=2000) as new_page_info:
                                                await link.click()

                                            new_page = await new_page_info.value
                                            await new_page.wait_for_load_state('domcontentloaded', timeout=3000)
                                            actual_url = new_page.url

                                            if os.getenv('DEBUG'):
                                                logger.debug(f"Link '{link_text}' opened new tab -> {actual_url}")

                                            extracted_links.append({
                                                'text': link_text,
                                                'url': actual_url
                                            })

                                            await new_page.close()

                                        except Exception as e:
                                            if os.getenv('DEBUG'):
                                                logger.debug(f"No new page opened for link: {e}")

                                    except Exception as link_err:
                                        if os.getenv('DEBUG'):
                                            logger.debug(f"Could not extract URL for link {i}: {link_err}")

                            except Exception as links_err:
                                if os.getenv('DEBUG'):
                                    logger.debug(f"Error extracting links: {links_err}")

                            # Add extracted links to homework/note text
                            if extracted_links:
                                links_str = "\n\nLinks:\n" + "\n".join(
                                    f"- {link['text']}: {link['url']}" for link in extracted_links
                                )
                                if popup_homework:
                                    popup_homework += links_str
                                elif popup_note:
                                    popup_note += links_str

                            # Close the popup by pressing Escape
                            await self.page.keyboard.press('Escape')

                        except Exception as popup_err:
                            if os.getenv('DEBUG'):
                                logger.debug(f"Could not open/parse popup: {popup_err}")

        except Exception as e:
            if os.getenv('DEBUG'):
                logger.debug(f"Error extracting popup details: {e}")

        # Use popup content if available, otherwise fall back to SVG tooltip content
        final_homework = popup_homework if popup_homework else homework_text
        final_note = popup_note if popup_note else note_text

        return {
            'id': lesson_id,
            'date': date,
            'weekday': weekday,
            'time': time,
            'subject': subject,
            'teacher': teacher,
            'room': room,
            'has_homework': bool(final_homework),
            'has_note': bool(final_note),
            'has_files': len(files) > 0 or has_files,
            'homework': final_homework,
            'note': final_note,
            'files': files
        }

    async def download_lesson_file(self, file_url: str, file_name: str, output_dir: str = "./downloads") -> Dict:
        """
        Download a file from a lesson to the specified directory.

        Args:
            file_url: URL of the file to download
            file_name: Name to save the file as
            output_dir: Directory to save the file in (default: ./downloads)

        Returns:
            {
                'success': bool,
                'file_path': str,
                'file_name': str,
                'error': str (if failed)
            }
        """
        import os
        from pathlib import Path

        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        try:
            os.makedirs(output_dir, exist_ok=True)

            safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
            file_path = os.path.join(output_dir, safe_filename)

            async with self.page.context.expect_download() as download_info:
                await self.page.goto(file_url)

            download = await download_info.value
            await download.save_as(file_path)

            file_size = os.path.getsize(file_path)

            return {
                'success': True,
                'file_path': file_path,
                'file_name': safe_filename,
                'file_size': file_size
            }

        except Exception as e:
            return {
                'success': False,
                'file_path': '',
                'file_name': file_name,
                'error': str(e)
            }

    async def load_lesson_file(self, file_url: str, file_name: str) -> Dict:
        """
        Load a file from a lesson and return its content for Claude to read.

        Args:
            file_url: URL of the file to load
            file_name: Name of the file

        Returns:
            {
                'success': bool,
                'file_name': str,
                'content': bytes or str,
                'content_type': str,
                'size': int,
                'error': str (if failed)
            }
        """
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        try:
            response = await self.page.context.request.get(file_url)

            if response.status != 200:
                return {
                    'success': False,
                    'file_name': file_name,
                    'content': None,
                    'error': f"HTTP {response.status}"
                }

            content = await response.body()
            content_type = response.headers.get('content-type', 'application/octet-stream')

            if 'text' in content_type or 'json' in content_type or 'xml' in content_type:
                try:
                    content_str = content.decode('utf-8')
                    return {
                        'success': True,
                        'file_name': file_name,
                        'content': content_str,
                        'content_type': content_type,
                        'size': len(content),
                        'is_text': True
                    }
                except:
                    pass

            import base64
            return {
                'success': True,
                'file_name': file_name,
                'content': base64.b64encode(content).decode('utf-8'),
                'content_type': content_type,
                'size': len(content),
                'is_text': False,
                'encoding': 'base64'
            }

        except Exception as e:
            return {
                'success': False,
                'file_name': file_name,
                'content': None,
                'error': str(e)
            }


async def main():
    async with StudiePlusScraper() as scraper:
        logger.info("Starting Studie+ scraper...")
        logger.info(f"School: {scraper.school}")
        logger.info(f"Username: {scraper.username}")

        homework = await scraper.get_homework()

        if homework:
            logger.info(f"HOMEWORK ASSIGNMENTS ({len(homework)} found)")

            for i, item in enumerate(homework, 1):
                logger.info(f"{i}. {item.get('subject', 'N/A')} - {item.get('title', 'N/A')}")
                logger.info(f"   Deadline: {item.get('deadline', 'N/A')}")
                logger.info(f"   Class: {item.get('class', 'N/A')} | Week: {item.get('week', 'N/A')}")
                logger.info(f"   Subject budget: {item.get('subject_budget_hours', 'N/A')} hours | Hours spent on assignment: {item.get('hours_spent', 'N/A')}")
        else:
            logger.warning("No homework found.")


if __name__ == "__main__":
    asyncio.run(main())
