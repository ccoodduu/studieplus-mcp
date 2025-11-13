import os
import asyncio
import re
from typing import List, Dict, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


class StudiePlusScraper:
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
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _attempt_login(self) -> bool:
        """Single login attempt. Returns True if successful, False otherwise."""
        try:
            print("[*] Navigating to Studie+ login page...")
            await self.page.goto("https://all.studieplus.dk/")
            await self.page.wait_for_load_state("networkidle", timeout=8000)

            print("[*] Waiting for Select2 to initialize...")
            await self.page.wait_for_selector(".select2-container", timeout=10000)
            print("[+] Select2 loaded")

            print(f"[*] Clicking Select2 dropdown...")
            await self.page.click(".select2-container")
            await asyncio.sleep(0.3)

            print(f"[*] Looking for school: {self.school}")
            search_input = await self.page.wait_for_selector(".select2-search input, .select2-input", timeout=5000)
            await search_input.type(self.school)
            await asyncio.sleep(0.3)

            result = await self.page.wait_for_selector(f".select2-results .select2-result:has-text('{self.school}')", timeout=5000)
            await result.click()

            await asyncio.sleep(0.3)
            print(f"[+] Selected school: {self.school}")

            await self.page.screenshot(path="before_login_button.png")
            print("[*] Screenshot saved")

            direkte_button = await self.page.wait_for_selector("button#direkte, button[name='how'][value='DIREKTE']", timeout=5000)
            await direkte_button.click()
            print("[+] Clicked 'Direkte' login button")

            print("[*] Waiting for login fields...")
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
                        print(f"[+] Found username field with selector: {selector}")
                        break
                except:
                    continue

            await self.page.screenshot(path="after_direkte_click.png")
            print("[*] Screenshot saved to after_direkte_click.png")

            if not username_field:
                raise Exception("Could not find username field")

            await username_field.fill(self.username)
            print(f"[+] Filled username: {self.username}")

            password_field = await self.page.wait_for_selector("input[name='password'], input[name='kodeord'], input[type='password']", timeout=5000)
            await password_field.fill(self.password)
            print("[+] Filled password")

            submit_button = await self.page.wait_for_selector("button[type='submit'], input[type='submit'], button:has-text('Log ind'), button:has-text('Login')", timeout=5000)
            await submit_button.click()
            print("[+] Clicked submit button")

            await self.page.wait_for_load_state("networkidle", timeout=10000)

            await self.page.screenshot(path="after_login.png")
            print("[*] Screenshot saved to after_login.png")

            current_url = self.page.url
            if "login" not in current_url.lower():
                print(f"[+] Login successful! Current URL: {current_url}")

                # Navigate to schedule page
                print("[*] Navigating to schedule page...")
                await self.page.goto("https://all.studieplus.dk/skema/")
                await self.page.wait_for_load_state("networkidle", timeout=10000)
                print(f"[+] Now on schedule page: {self.page.url}")

                self.logged_in = True
                return True
            else:
                print(f"[-] Login may have failed. Still on: {current_url}")
                return False

        except Exception as e:
            print(f"[-] Login attempt error: {e}")
            try:
                await self.page.screenshot(path="error_page.png")
                print("[*] Error screenshot saved to error_page.png")
            except:
                pass
            return False

    async def login(self) -> bool:
        """Login with automatic retry (max 3 attempts)."""
        if self.logged_in:
            print("[*] Already logged in, skipping login")
            return True

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            print(f"\n[*] Login attempt {attempt}/{max_attempts}")

            success = await self._attempt_login()

            if success:
                return True

            if attempt < max_attempts:
                print(f"[!] Login attempt {attempt} failed, retrying...")
                await asyncio.sleep(1)
            else:
                print(f"[-] All {max_attempts} login attempts failed")
                return False

        return False

    async def get_homework(self) -> List[Dict]:
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        print("\n[*] Looking for Assignments link in menu...")

        try:
            assignments_link = await self.page.wait_for_selector("a:has-text('Assignments'), a:has-text('Opgaver')", timeout=5000)
            await assignments_link.click()
            print("[+] Clicked Assignments link")

            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.5)

            await self.page.screenshot(path="assignments_page.png")
            print("[*] Screenshot saved to assignments_page.png")

            homework_data = await self._extract_homework_from_page()

            if homework_data:
                return homework_data

            print("\n[*] Extracting all visible text from assignments page...")
            visible_text = await self.page.evaluate("""() => {
                return document.body.innerText;
            }""")

            with open("assignments_text.txt", "w", encoding="utf-8") as f:
                f.write(visible_text)
            print("[+] Saved assignments page text to assignments_text.txt")

            content = await self.page.content()
            with open("assignments_page.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("[+] Saved assignments HTML to assignments_page.html")

            return []

        except Exception as e:
            print(f"[-] Error accessing assignments: {e}")

            await self.page.screenshot(path="error_assignments.png")
            print("[*] Error screenshot saved")

            return []

    async def _extract_homework_from_page(self) -> List[Dict]:
        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        with open("assignments_page.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("[*] Saved assignments HTML")

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
            print(f"[+] Found {len(homework_items)} homework assignments")
            return homework_items

        return []

    async def get_assignment_details(self, row_index: str) -> Dict:
        if not self.page:
            raise Exception("Browser not started. Call start() first.")

        login_success = await self.login()
        if not login_success:
            raise Exception("Login failed")

        print(f"\n[*] Fetching assignment details for row {row_index}")

        try:
            print("[*] Navigating to assignments page...")
            assignments_link = await self.page.wait_for_selector("a:has-text('Assignments'), a:has-text('Opgaver')", timeout=5000)
            await assignments_link.click()
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.5)

            print(f"[*] Looking for 'Detaljer' button in row {row_index}")
            details_button = await self.page.wait_for_selector(
                f'tr[__gwt_row="{row_index}"] button:has-text("Detaljer")',
                timeout=10000
            )

            if details_button:
                await details_button.click()
                print("[+] Clicked 'Detaljer' button")

                await asyncio.sleep(1.5)

                iframe_description = ""
                try:
                    iframe_locator = self.page.frame_locator('iframe.gwt-RichTextArea')
                    iframe_body = iframe_locator.locator('body')
                    iframe_description = await iframe_body.inner_text(timeout=3000)
                    print(f"[+] Got description from iframe: {iframe_description[:100]}...")
                except Exception as e:
                    print(f"[*] No iframe description found: {e}")

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

                table_rows = soup.find_all('tr')
                for row in table_rows:
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)

                        if 'Opgavetitel' in label:
                            result['assignment_title'] = value
                        elif 'Fag/hold' in label:
                            result['subject'] = value
                        elif 'Fordybelsestid' in label:
                            result['student_time'] = value
                        elif 'Ansvarlig' in label:
                            result['responsible'] = value
                        elif 'Forløb' in label:
                            result['course'] = value
                        elif 'Bedømmelsesform' in label:
                            result['evaluation_form'] = value
                        elif 'Grupper' in label:
                            result['groups'] = value

                status_divs = soup.find_all('div', class_='gwt-Label')
                for div in status_divs:
                    text = div.get_text(strip=True)
                    if 'Afleveringsstatus' in text:
                        next_elem = div.find_next('h3')
                        if next_elem:
                            result['submission_status'] = next_elem.get_text(strip=True)
                    elif 'Afleveringsfrist' in text:
                        next_elem = div.find_next('div', class_='gwt-Label')
                        if next_elem and ':' in next_elem.get_text():
                            result['deadline'] = next_elem.get_text(strip=True)

                if iframe_description and len(iframe_description.strip()) > 0:
                    result['description'] = iframe_description.strip()
                else:
                    desc_headers = soup.find_all('h4')
                    description_parts = []
                    for header in desc_headers:
                        header_text = header.get_text(strip=True)
                        if 'Opgaveformulering' in header_text:
                            next_sibling = header.find_next_sibling()
                            if next_sibling:
                                desc_text = next_sibling.get_text(strip=True)
                                if desc_text and desc_text != 'Ingen filer' and len(desc_text) > 5:
                                    description_parts.append(desc_text)

                    if description_parts:
                        result['description'] = '\n\n'.join(description_parts)

                file_links = soup.find_all('a', href=True)
                for link in file_links:
                    href = link.get('href', '')
                    link_text = link.get_text(strip=True)
                    if (('/filer/' in href or '/bilag/' in href or
                         href.endswith(('.pdf', '.docx', '.xlsx', '.pptx', '.zip', '.doc', '.txt')))
                        and link_text and len(link_text) > 2):
                        result['files'].append({
                            'name': link_text,
                            'url': href
                        })

                await self.page.screenshot(path="assignment_details.png")
                print("[*] Screenshot saved to assignment_details.png")

                with open("assignment_details.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("[*] Saved assignment HTML to assignment_details.html")

                return result

        except Exception as e:
            print(f"[-] Error fetching assignment details: {e}")
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

        print("\n[*] Parsing schedule homework from SVG...")

        # Wait for SVG to load
        await asyncio.sleep(2)

        # Get HTML content
        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Find all lesson SVG groups
        lesson_groups = soup.find_all('g', class_='CAHE1CD-h-b')
        print(f"[+] Found {len(lesson_groups)} lessons in schedule")

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

        print(f"[+] Found {len(homework_list)} lessons with homework/notes")
        return homework_list

    def parse_week_dates(self, soup: BeautifulSoup) -> tuple[List[str], str, str]:
        """
        Extract dates, week number, and year from schedule HTML.

        Args:
            soup: BeautifulSoup object of schedule page

        Returns:
            Tuple of (dates_list, week_number, year)
            - dates_list: List of 7 ISO dates ["2025-11-10", ...]
            - week_number: Week number as string ("46")
            - year: Year as string ("2025")
        """
        weekdays = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]
        dates = []

        date_labels = soup.find_all('div', class_='gwt-Label')

        week_info = None
        for label in date_labels:
            text = label.get_text(strip=True)
            if "Uge" in text and "-" in text:
                week_info = text
                break

        if not week_info:
            buttons = soup.find_all('button')
            for btn in buttons:
                text = btn.get_text(strip=True)
                if "Uge" in text and "-" in text:
                    week_info = text
                    break

        if not week_info:
            raise Exception("Could not find week information in schedule")

        week_match = re.search(r'Uge (\d+) - (\d{4})', week_info)
        if not week_match:
            raise Exception(f"Could not parse week info: {week_info}")

        week_number = week_match.group(1)
        year = week_match.group(2)

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

    def calculate_lesson_date(self, transform: str, week_dates: List[str]) -> tuple[str, str]:
        """
        Calculate lesson date and weekday from SVG transform position.

        Args:
            transform: SVG transform attribute (e.g., "translate(197, 600) rotate(0)")
            week_dates: List of 7 ISO dates for the week

        Returns:
            Tuple of (iso_date, weekday_name)
        """
        weekday_names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

        match = re.search(r'translate\((\d+),\s*(\d+)\)', transform)
        if not match:
            return (week_dates[0], weekday_names[0])

        x_pos = int(match.group(1))

        day_index = x_pos // 197

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
                print(f"[!] Warning: Could not navigate week: {e}")
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

        week_dates, week_number, year = self.parse_week_dates(soup)

        lesson_groups = soup.find_all('g', class_='CAHE1CD-h-b')
        print(f"[+] Found {len(lesson_groups)} lessons in schedule")

        lessons = []

        for lesson in lesson_groups:
            transform = lesson.get('transform', '')
            if not transform:
                continue

            lesson_date, weekday = self.calculate_lesson_date(transform, week_dates)

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
                text_content = text_elem.get_text(strip=True)

                if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', text_content):
                    time = text_content

                if text_elem.get('style', '') and 'font-weight: bold' in text_elem.get('style'):
                    if ':' not in text_content:
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

                    if '*** Lektier ***' in title_content or '*** Homework ***' in title_content:
                        has_homework = True

                    if '*** Noter ***' in title_content or '*** Notes ***' in title_content:
                        has_note = True

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

        print(f"[+] Parsed {len(lessons)} valid lessons")
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

        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')

        week_dates, week_number, year = self.parse_week_dates(soup)

        lesson_groups = soup.find_all('g', class_='CAHE1CD-h-b')

        target_lesson = None
        for lesson in lesson_groups:
            transform = lesson.get('transform', '')
            if not transform:
                continue

            lesson_date, weekday = self.calculate_lesson_date(transform, week_dates)

            if lesson_date != date:
                continue

            texts = lesson.find_all('text')
            lesson_time = ""

            for text_elem in texts:
                text_content = text_elem.get_text(strip=True)
                if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', text_content):
                    lesson_time = text_content
                    break

            if lesson_time == time:
                target_lesson = lesson
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
            text_content = text_elem.get_text(strip=True)

            if text_elem.get('style', '') and 'font-weight: bold' in text_elem.get('style'):
                if ':' not in text_content:
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
        if has_files:
            try:
                bbox = target_lesson.find('rect').get('transform', '')
                if bbox:
                    match = re.search(r'translate\((\d+),\s*(\d+)\)', bbox)
                    if match:
                        x, y = int(match.group(1)), int(match.group(2))
                        await self.page.mouse.click(x + 50, y + 20, force=True)
                        await self.page.wait_for_load_state('domcontentloaded', timeout=2000)

                        await self.page.keyboard.press('Control+Alt+N')
                        await self.page.wait_for_load_state('domcontentloaded', timeout=2000)

                        panel_content = await self.page.content()
                        panel_soup = BeautifulSoup(panel_content, 'html.parser')

                        file_links = panel_soup.find_all('a', href=True)
                        for link in file_links:
                            href = link.get('href', '')
                            if 'download' in href or 'file' in href.lower():
                                file_name = link.get_text(strip=True)
                                if file_name:
                                    files.append({
                                        'name': file_name,
                                        'url': href if href.startswith('http') else f"https://all.studieplus.dk{href}"
                                    })

                        await self.page.keyboard.press('Escape')
            except Exception as e:
                print(f"[!] Warning: Could not extract files: {e}")

        return {
            'id': lesson_id,
            'date': date,
            'weekday': weekday,
            'time': time,
            'subject': subject,
            'teacher': teacher,
            'room': room,
            'has_homework': bool(homework_text),
            'has_note': bool(note_text),
            'has_files': has_files,
            'homework': homework_text,
            'note': note_text,
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
        print("[*] Starting Studie+ scraper...")
        print(f"[*] School: {scraper.school}")
        print(f"[*] Username: {scraper.username}")

        homework = await scraper.get_homework()

        if homework:
            print(f"\n\n{'='*60}")
            print(f"HOMEWORK ASSIGNMENTS ({len(homework)} found)")
            print(f"{'='*60}\n")

            for i, item in enumerate(homework, 1):
                print(f"{i}. {item.get('subject', 'N/A')} - {item.get('title', 'N/A')}")
                print(f"   Deadline: {item.get('deadline', 'N/A')}")
                print(f"   Class: {item.get('class', 'N/A')} | Week: {item.get('week', 'N/A')}")
                print(f"   Subject budget: {item.get('subject_budget_hours', 'N/A')} hours | Hours spent on assignment: {item.get('hours_spent', 'N/A')}")
                print()

            print(f"{'='*60}\n")
        else:
            print("\n[!] No homework found.")


if __name__ == "__main__":
    asyncio.run(main())
