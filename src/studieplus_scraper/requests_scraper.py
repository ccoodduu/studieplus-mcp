import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv
from .scraper import debug_path
from .logger import logger

load_dotenv()


class StudiePlusRequestsScraper:
    def __init__(self, username: str = None, password: str = None, school: str = None):
        self.username = username or os.getenv("STUDIEPLUS_USERNAME")
        self.password = password or os.getenv("STUDIEPLUS_PASSWORD")
        self.school = school or os.getenv("STUDIEPLUS_SCHOOL")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = "https://all.studieplus.dk"

    def _find_school_instnr(self) -> Optional[str]:
        logger.info(f"Looking up school: {self.school}")

        response = self.session.get(f"{self.base_url}/")
        soup = BeautifulSoup(response.text, 'html.parser')

        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and 'const data = JSON.parse' in script.string:
                import re
                import json

                match = re.search(r'const data = JSON\.parse\(\'(.+?)\'\);', script.string)
                if match:
                    json_str = match.group(1)
                    json_str = json_str.replace('\\', '')

                    schools = json.loads(json_str)

                    for school in schools:
                        if school.get('navn') == self.school:
                            logger.info(f"Found school with instnr: {school['instnr']}")
                            return school['instnr']

        logger.error(f"Could not find school: {self.school}")
        return None

    def login(self) -> bool:
        try:
            logger.info("Logging in to Studie+...")

            instnr = self._find_school_instnr()
            if not instnr:
                return False

            self.session.cookies.set('instkey', instnr)
            self.session.cookies.set('instnr', instnr)

            login_data = {
                'instnr': instnr,
                'how': 'DIREKTE',
                'user': self.username,
                'pass': self.password
            }

            response = self.session.post(
                f"{self.base_url}/login/doLogin",
                data=login_data,
                allow_redirects=True
            )

            if 'skema' in response.url or 'forside' in response.url:
                logger.info(f"Login successful! Redirected to: {response.url}")
                return True
            else:
                logger.error(f"Login failed. Current URL: {response.url}")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def get_homework(self) -> List[Dict]:
        if not self.login():
            raise Exception("Login failed")

        logger.info("Fetching homework assignments...")

        try:
            response = self.session.get(f"{self.base_url}/opgave/?id=id_menu_opgaver")

            if response.status_code != 200:
                logger.error(f"Failed to fetch assignments page: {response.status_code}")
                return []

            with open(debug_path("opgave_page.html"), "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.debug(f"Saved HTML to {debug_path('opgave_page.html')}")

            soup = BeautifulSoup(response.text, 'html.parser')

            homework_items = []
            assignment_table = soup.find('table')

            if assignment_table:
                rows = assignment_table.find_all('tr')

                for row in rows:
                    cols = row.find_all('td')

                    if len(cols) >= 6:
                        subject = cols[0].get_text(strip=True)
                        title = cols[1].get_text(strip=True)
                        pulje = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                        brugt = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                        class_name = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                        week = cols[5].get_text(strip=True) if len(cols) > 5 else ""
                        deadline = cols[6].get_text(strip=True) if len(cols) > 6 else ""

                        if subject and title:
                            homework_items.append({
                                'subject': subject,
                                'title': title,
                                'subject_budget_hours': pulje,
                                'hours_spent': brugt,
                                'class': class_name,
                                'week': week,
                                'deadline': deadline
                            })

            if homework_items:
                logger.info(f"Found {len(homework_items)} homework assignments")
                return homework_items

            logger.warning("No homework found")
            return []

        except Exception as e:
            logger.error(f"Error fetching homework: {e}")
            return []


def main():
    scraper = StudiePlusRequestsScraper()

    logger.info("Starting Studie+ requests scraper (fast mode)...")
    logger.info(f"School: {scraper.school}")
    logger.info(f"Username: {scraper.username}")

    homework = scraper.get_homework()

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
    main()
