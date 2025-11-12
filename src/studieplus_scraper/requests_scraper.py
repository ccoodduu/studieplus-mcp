import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv

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
        print(f"[*] Looking up school: {self.school}")

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
                            print(f"[+] Found school with instnr: {school['instnr']}")
                            return school['instnr']

        print(f"[-] Could not find school: {self.school}")
        return None

    def login(self) -> bool:
        try:
            print("[*] Logging in to Studie+...")

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
                print(f"[+] Login successful! Redirected to: {response.url}")
                return True
            else:
                print(f"[-] Login failed. Current URL: {response.url}")
                return False

        except Exception as e:
            print(f"[-] Login error: {e}")
            return False

    def get_homework(self) -> List[Dict]:
        if not self.login():
            raise Exception("Login failed")

        print("\n[*] Fetching homework assignments...")

        try:
            response = self.session.get(f"{self.base_url}/opgave/?id=id_menu_opgaver")

            if response.status_code != 200:
                print(f"[-] Failed to fetch assignments page: {response.status_code}")
                return []

            with open("opgave_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("[*] Saved HTML to opgave_page.html")

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
                print(f"[+] Found {len(homework_items)} homework assignments")
                return homework_items

            print("[-] No homework found")
            return []

        except Exception as e:
            print(f"[-] Error fetching homework: {e}")
            return []


def main():
    scraper = StudiePlusRequestsScraper()

    print("[*] Starting Studie+ requests scraper (fast mode)...")
    print(f"[*] School: {scraper.school}")
    print(f"[*] Username: {scraper.username}")

    homework = scraper.get_homework()

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
    main()
