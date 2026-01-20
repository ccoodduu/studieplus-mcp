"""
Lightweight HTTP-based scraper for StudiePlus using GWT-RPC API.
No browser required - runs on Raspberry Pi with minimal RAM (~30MB vs ~300MB for Playwright).
"""
import requests
import os
import re
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv
from .logger import logger
from .base_scraper import BaseStudiePlusScraper
from .gwt_deserializer import GWTScheduleParser, parse_schedule_response, GWTDeserializer

load_dotenv()

DEBUG_SAVE_RAW_RESPONSES = True


class GWTParser:
    """Parser for GWT-RPC responses."""

    def __init__(self, response_text: str):
        self.raw = response_text
        self.string_table = []
        self.data = []

        if response_text.startswith('//OK['):
            self._parse_response(response_text[5:-1])
        elif response_text.startswith('//EX['):
            raise Exception(f"GWT Exception: {response_text}")
        else:
            raise Exception(f"Unknown GWT response format")

    def _parse_response(self, content: str):
        """Parse the GWT-RPC response content."""
        bracket_start = content.rfind('[')
        bracket_end = content.rfind(']') + 1

        if bracket_start == -1:
            raise Exception("Could not find string table")

        string_table_str = content[bracket_start:bracket_end]
        self._parse_string_table(string_table_str)

        data_str = content[:bracket_start].rstrip(',')
        self._parse_data(data_str)

    def _parse_string_table(self, s: str):
        """Parse the string table."""
        self.string_table = []
        current = ""
        in_string = False
        escape = False

        for char in s[1:-1]:
            if escape:
                current += char
                escape = False
            elif char == '\\':
                escape = True
                current += char
            elif char == '"':
                if in_string:
                    try:
                        decoded = current.encode().decode('unicode_escape')
                    except:
                        decoded = current
                    self.string_table.append(decoded)
                    current = ""
                    in_string = False
                else:
                    in_string = True
            elif in_string:
                current += char

    def _parse_data(self, s: str):
        """Parse the data array."""
        self.data = []
        for part in s.split(','):
            part = part.strip()
            if not part:
                continue
            try:
                if '.' in part:
                    self.data.append(float(part))
                else:
                    self.data.append(int(part))
            except ValueError:
                self.data.append(part)

    def get_string(self, index: int) -> Optional[str]:
        """Get string from table by index."""
        if 0 <= index < len(self.string_table):
            return self.string_table[index]
        return None


class StudiePlusRequestsScraper(BaseStudiePlusScraper):
    """HTTP-based scraper for StudiePlus using GWT-RPC API."""

    def __init__(self, username: str = None, password: str = None, school: str = None):
        self.username = username or os.getenv("STUDIEPLUS_USERNAME")
        self.password = password or os.getenv("STUDIEPLUS_PASSWORD")
        self.school = school or os.getenv("STUDIEPLUS_SCHOOL")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = "https://all.studieplus.dk"
        self.logged_in = False

        # GWT module hashes - may need updates when StudiePlus updates
        self.skema_permutation = "B0742ABB769CAA45E3CD75BA219C6E04"
        self.opgave_permutation = "ED91C3E5761A98C33045A799A1B8B8B1"

    def _find_school_instnr(self) -> Optional[str]:
        """Find school institution number."""
        logger.info(f"Looking up school: {self.school}")
        response = self.session.get(f"{self.base_url}/")

        match = re.search(r"const data = JSON\.parse\('(.+?)'\);", response.text)
        if match:
            json_str = match.group(1).replace('\\', '')
            schools = json.loads(json_str)
            for school in schools:
                if school.get('navn') == self.school:
                    logger.info(f"Found school instnr: {school['instnr']}")
                    return school['instnr']

        logger.error(f"Could not find school: {self.school}")
        return None

    def login(self) -> bool:
        """Login to StudiePlus."""
        if self.logged_in:
            return True

        try:
            instnr = self._find_school_instnr()
            if not instnr:
                return False

            self.session.cookies.set('instkey', instnr)
            self.session.cookies.set('instnr', instnr)

            self.session.post(f"{self.base_url}/login/doLogin", data={
                'instnr': instnr,
                'acr_values': '',
                'how': 'DIREKTE'
            })

            response = self.session.post(
                f"{self.base_url}/login/doLogin",
                data={
                    'instnr': instnr,
                    'user': self.username,
                    'pass': self.password,
                    'how': 'DIREKTE'
                },
                allow_redirects=True
            )

            if 'skema' in response.url or 'forside' in response.url:
                logger.info("Login successful!")
                self.logged_in = True
                return True

            logger.error(f"Login failed. URL: {response.url}")
            return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def _make_gwt_call(self, service_url: str, payload: str, permutation: str, module: str) -> str:
        """Make a GWT-RPC call."""
        headers = {
            'Content-Type': 'text/x-gwt-rpc; charset=UTF-8',
            'X-GWT-Permutation': permutation,
            'X-GWT-Module-Base': f"{self.base_url}/{module}/{module}/",
            'modulename': module
        }
        response = self.session.post(service_url, data=payload, headers=headers)
        return response.text

    def _encode_date(self, dt: datetime) -> str:
        """Encode datetime for GWT-RPC."""
        year = dt.year - 1900
        return f"5|6|{year}|{dt.month - 1}|{dt.day}|0|0|0|"

    # ============================================================
    # RESSOURCE/FILES API
    # ============================================================

    def get_lesson_files(self, skema_id: int) -> List[Dict]:
        """
        Get files attached to a lesson via ressourceservice.findRessourcerPerContainer.

        Args:
            skema_id: The lesson ID from SkemaBegivenhed

        Returns:
            List of file dicts: [{'name': str, 'id': int}, ...]
        """
        if not self.login():
            return []

        # GWT-RPC payload for findRessourcerPerContainer
        # Format from Chrome DevTools capture:
        # 7|0|6|base_url|hash|service|method|RessourceKey|RessourceObjektType|1|2|3|4|1|5|5|skema_id|6|12|
        payload = (
            "7|0|6|"
            f"{self.base_url}/skema/skema/|"
            "09D4724C79CC98B839803FCB9CBF2218|"
            "dk.uddata.services.interfaces.RessourceService|"
            "findRessourcerPerContainer|"
            "dk.uddata.model.ressourcer.RessourceKey/785242658|"
            "dk.uddata.model.ressourcer.RessourceObjektType/3745084519|"
            f"1|2|3|4|1|5|5|{skema_id}|6|12|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/skema/ressourceservice",
                payload,
                self.skema_permutation,
                "skema"
            )

            if response.startswith('//OK'):
                return self._parse_ressource_response(response)
            else:
                logger.debug(f"Ressource fetch failed for skema_id={skema_id}: {response[:200]}")
                return []
        except Exception as e:
            logger.debug(f"Error fetching ressources for skema_id={skema_id}: {e}")
            return []

    def _parse_ressource_response(self, response: str) -> List[Dict]:
        """
        Parse findRessourcerPerContainer response using proper GWT structure.

        Ressource structure (from cYf deserializer):
        b.c = int (skema_id)
        b.d = pqd string (file name)
        b.e = int (file ID!)
        b.f = pqd string (UUID)
        b.g = object (Type)

        Response is an ArrayList of Ressource objects.
        """
        try:
            parser = GWTParser(response)
            strings = parser.string_table
            data = parser.data

            files = []

            # Find class markers in string table
            ressource_marker = None
            for i, s in enumerate(strings):
                if s and s.startswith('dk.uddata.model.ressourcer.Ressource/'):
                    ressource_marker = i + 1  # 1-based indexing
                    break

            if not ressource_marker:
                return []

            # Find each Ressource instance by finding the class marker in data
            # Then read fields in stack order (backwards from marker position)
            i = 0
            while i < len(data):
                if data[i] == ressource_marker:
                    # Found a Ressource, read its fields (backwards from here)
                    # Stack order: marker is last, then fields in reverse order
                    # So reading forward from before the marker:
                    # pos-5: Type object marker (or back-ref)
                    # pos-4: f_idx (UUID string index) OR the actual index value
                    # pos-3: e (file ID - int)
                    # pos-2: d_idx (file name string index) OR the actual index value
                    # pos-1: c (skema_id - int)
                    # pos: marker

                    try:
                        # We need to handle pqd pattern: val > 0 ? strings[val-1] : null
                        # This means: if val > 0, it's a string index, else null

                        # c (skema_id) - position i-1
                        c = data[i - 1] if i >= 1 else 0

                        # d (file name) - pqd at position i-2
                        # pqd reads: val = pop(); if val > 0: return strings[val-1]
                        d_idx = data[i - 2] if i >= 2 else 0
                        file_name = strings[d_idx - 1] if d_idx > 0 and d_idx <= len(strings) else None

                        # e (file ID) - position i-3
                        file_id = data[i - 3] if i >= 3 else 0

                        # f (UUID) - pqd at position i-4
                        f_idx = data[i - 4] if i >= 4 else 0
                        uuid = strings[f_idx - 1] if f_idx > 0 and f_idx <= len(strings) else None

                        if file_name and isinstance(file_id, int) and file_id > 0:
                            files.append({
                                'name': file_name,
                                'id': file_id,
                                'uuid': uuid
                            })
                    except (IndexError, TypeError):
                        pass

                i += 1

            return files

        except Exception as e:
            logger.debug(f"Error parsing ressource response: {e}")
            return []

    def get_file_download_url(self, file_id: int) -> Optional[str]:
        """
        Get the signed download URL for a file via hentRessourceUrl.

        Args:
            file_id: The ressource/file ID

        Returns:
            Signed S3 URL for downloading the file, or None on error
        """
        if not self.login():
            return None

        # GWT-RPC payload for hentRessourceUrl
        # Method: hentRessourceUrl(int fileId, String empty)
        payload = (
            "7|0|7|"
            f"{self.base_url}/skema/skema/|"
            "09D4724C79CC98B839803FCB9CBF2218|"
            "dk.uddata.services.interfaces.RessourceService|"
            "hentRessourceUrl|"
            "I|"
            "java.lang.String/2004016611|"
            "|"  # empty string
            f"1|2|3|4|2|5|6|{file_id}|7|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/skema/ressourceservice",
                payload,
                self.skema_permutation,
                "skema"
            )

            if response.startswith('//OK'):
                # Response format: //OK[1, ["https://...signed-url..."], 0, 7]
                # Parse to extract URL
                import json
                content = response[4:]  # Remove //OK prefix
                parsed = json.loads(content)
                # URL is in the array at index 1
                if len(parsed) > 1 and isinstance(parsed[1], list) and len(parsed[1]) > 0:
                    return parsed[1][0]
            else:
                logger.debug(f"hentRessourceUrl failed for file_id={file_id}: {response[:100]}")

            return None
        except Exception as e:
            logger.debug(f"Error getting download URL for file_id={file_id}: {e}")
            return None

    def get_lesson_files_with_urls(self, skema_id: int) -> List[Dict]:
        """
        Get files for a lesson with download URLs.

        Convenience method that combines get_lesson_files and get_file_download_url.

        Args:
            skema_id: The lesson ID

        Returns:
            List of file dicts: [{'name': str, 'id': int, 'url': str}, ...]
        """
        files = self.get_lesson_files(skema_id)

        for f in files:
            if f.get('id'):
                url = self.get_file_download_url(f['id'])
                f['url'] = url or ''

        return files

    # ============================================================
    # SCHEDULE NOTES API (for has_files detection)
    # ============================================================

    def get_note_for_skema(self, skema_id: int) -> Optional[Dict]:
        """
        Fetch SkemaNote2 for a specific lesson.

        Returns dict with:
        - has_files: bool (from SkemaNote2.d)
        - homework_text: str (from SkemaNote2.e)
        - note_text: str (from SkemaNote2.g)
        """
        if not self.login():
            return None

        # GWT-RPC payload for hentNoteForSkema
        # Service: skemanoteservice, Hash: EB1BAA9F2AD8A53B59DC22F1082E0E1B
        payload = (
            "7|0|5|"
            f"{self.base_url}/skema/skema/|"
            "EB1BAA9F2AD8A53B59DC22F1082E0E1B|"
            "dk.uddata.services.interfaces.SkemaNote2Service|"
            "hentNoteForSkema|"
            "I|"
            f"1|2|3|4|1|5|{skema_id}|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/skema/skemanoteservice",
                payload,
                self.skema_permutation,
                "skema"
            )

            if response.startswith('//OK'):
                return self._parse_skema_note_response(response)
            else:
                logger.debug(f"Note fetch failed for skema_id={skema_id}: {response[:100]}")
                return None
        except Exception as e:
            logger.debug(f"Error fetching note for skema_id={skema_id}: {e}")
            return None

    def _parse_skema_note_response(self, response: str) -> Optional[Dict]:
        """Parse SkemaNote2 response to extract has_files and other fields."""
        try:
            parser = GWTParser(response)
            data = parser.data
            strings = parser.string_table

            # SkemaNote2 structure (from JS hAg function):
            # b.a = int
            # b.b = string
            # b.c = int
            # b.d = boolean (HAS_FILES!)
            # b.e = string (homework text)
            # b.f = string (homework HTML)
            # b.g = string (note text)
            # b.i = string (note HTML)
            # ... more fields

            # Find SkemaNote2 class marker
            note_marker = None
            for i, s in enumerate(strings):
                if s and 'SkemaNote2/' in s:
                    note_marker = i + 1  # 1-based index
                    break

            if not note_marker:
                return {'has_files': False}

            # Find position of SkemaNote2 marker in data
            for i, val in enumerate(data):
                if val == note_marker and i > 5:
                    # Read fields from position before the marker
                    # Stack is read backwards, so fields are: a, b_idx, c, d, e_idx, f_idx, g_idx, i_idx...
                    pos = i - 1

                    # Try to extract has_files (field d is a boolean)
                    # Based on JS: b.d = !!a.b[--a.a] - it's the 4th field
                    # Fields order in data (before marker): s, r, q, p, o, n, k, j, i, g, f, e, d, c, b, a
                    # So field d is at position -13 from marker (counting backwards)

                    # Simplified approach: scan for boolean pattern
                    # has_files is a 0 or 1 int
                    has_files = False

                    # Look for the boolean field pattern
                    for offset in range(3, min(16, pos)):
                        val_at = data[pos - offset] if pos - offset >= 0 else None
                        # Boolean in GWT is 0 or 1
                        if val_at in [0, 1] and pos - offset - 1 >= 0:
                            # Check if it's the has_files field (preceded by an int)
                            prev_val = data[pos - offset - 1]
                            if isinstance(prev_val, int) and prev_val >= 0:
                                has_files = bool(val_at)
                                break

                    return {'has_files': has_files}

            return {'has_files': False}

        except Exception as e:
            logger.debug(f"Error parsing note response: {e}")
            return {'has_files': False}

    # ============================================================
    # SCHEDULE API
    # ============================================================

    def get_schedule_raw(self, start_date: datetime = None, end_date: datetime = None) -> str:
        """Get raw schedule data via GWT-RPC."""
        if not self.login():
            raise Exception("Login failed")

        if start_date is None:
            start_date = datetime.now()
        if end_date is None:
            end_date = start_date + timedelta(days=6)

        payload = (
            "7|0|6|"
            f"{self.base_url}/skema/skema/|"
            "83C0398D428292FBFA6ED34FEEEA605B|"
            "dk.uddata.services.interfaces.SkemaService|"
            "hentEgnePersSkemaData|"
            "dk.uddata.gwt.comm.shared.UDate/2314285719|"
            "UDate:|"
            "1|2|3|4|2|5|5|"
            f"{self._encode_date(start_date)}"
            f"{self._encode_date(end_date)}"
        )

        response = self._make_gwt_call(
            f"{self.base_url}/skema/skema/skemaservice",
            payload,
            self.skema_permutation,
            "skema"
        )

        if DEBUG_SAVE_RAW_RESPONSES:
            debug_file = f"debug_gwt_response_{start_date.strftime('%Y%m%d')}.txt"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(response)
            logger.info(f"Saved raw GWT response to {debug_file}")

        return response

    async def parse_schedule(self, week_offset: int = 0, fetch_notes: bool = False) -> Tuple[List[Dict], str, str, List[str]]:
        """
        Parse schedule and return lessons in same format as Playwright scraper.

        Args:
            week_offset: Weeks from current (0=this week, 1=next week, -1=last week)
            fetch_notes: If True, makes additional API calls to get has_files info

        Returns: (lessons, week_number, year, dates)
        """
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_date = start_of_week + timedelta(weeks=week_offset)
        end_date = start_date + timedelta(days=6)

        response = self.get_schedule_raw(start_date, end_date)

        week_number = str(start_date.isocalendar()[1])
        year = str(start_date.year)
        dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

        # Use the GWT deserializer to parse lessons
        gwt_lessons = parse_schedule_response(response)

        # Build a map from lesson_id to has_files if fetch_notes is enabled
        lesson_notes = {}
        if fetch_notes:
            # Get unique lesson IDs
            unique_ids = set(gl.lesson_id for gl in gwt_lessons if gl.lesson_id > 0)
            logger.info(f"Fetching notes for {len(unique_ids)} unique lessons...")

            for lesson_id in unique_ids:
                note_data = self.get_note_for_skema(lesson_id)
                if note_data:
                    lesson_notes[lesson_id] = note_data

        # Convert to dict format compatible with existing API
        weekday_names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
        lessons = []

        for gl in gwt_lessons:
            if not gl.start_time:
                continue

            lesson_date = gl.start_time.strftime('%Y-%m-%d')
            time_str = f"{gl.start_time.strftime('%H:%M')}-{gl.end_time.strftime('%H:%M')}"
            weekday = weekday_names[gl.start_time.weekday()]

            # Get has_files from notes if available
            has_files = False
            if gl.lesson_id in lesson_notes:
                has_files = lesson_notes[gl.lesson_id].get('has_files', False)

            lesson = {
                'id': f"{lesson_date}_{gl.start_time.strftime('%H:%M')}",
                'lesson_id': gl.lesson_id,  # Include raw lesson_id for debugging
                'date': lesson_date,
                'weekday': weekday,
                'time': time_str,
                'subject': gl.subject or "",
                'teacher': ", ".join(gl.teachers) if gl.teachers else "",
                'room': ", ".join(gl.rooms) if gl.rooms else "",
                'has_homework': gl.has_homework,
                'has_note': gl.has_note,
                'has_files': has_files,
                'homework': gl.homework or "",  # Homework text from SkemaNote2
                'note': gl.note or "",  # Note text from SkemaNote2
            }
            lessons.append(lesson)

        # Sort by date and time
        lessons.sort(key=lambda x: (x['date'], x['time']))

        return (lessons, week_number, year, dates)

    def _extract_lessons(self, parser: GWTParser, week_dates: List[str], year: int, month: int) -> List[Dict]:
        """Extract lessons from parsed GWT response using -714 marker pattern."""
        strings = parser.string_table
        data = parser.data

        # Build lookup tables from string table
        subjects = {}
        teachers = {}
        rooms = {}

        # Build a set of "placeholder" string indices (subject names, short strings)
        # These are NOT actual content - used to detect empty slots
        placeholder_indices = set()
        content_indices = set()  # Indices with actual content (HTML, longer text)

        for i, s in enumerate(strings):
            if not s:
                placeholder_indices.add(i)
                continue
            # Subject names and short strings are placeholders
            if len(s) < 30 and '<' not in s and '(' not in s:
                placeholder_indices.add(i)
            # HTML content or longer strings are actual content
            if '<font' in s.lower() or '<div' in s.lower() or len(s) > 50:
                content_indices.add(i)

        # Parse summary blocks to find NOTE and HW flags
        # Summary blocks: 28 positions, lesson_id at +0, day at +6, year at +8
        # +16/+17 = NOTE content (if not placeholder)
        # +18/+19 = HW content (if not placeholder)
        lessons_with_homework = set()  # (lesson_id, day) tuples
        lessons_with_notes = set()     # (lesson_id, day) tuples

        i = 0
        while i < min(500, len(data) - 25):
            val = data[i]
            if isinstance(val, int) and 400000 < val < 500000:
                lesson_id = val
                # Verify this is a summary block by checking year marker at +8
                if i + 8 < len(data) and isinstance(data[i + 8], int) and data[i + 8] in [124, 125, 126, 127]:
                    # Get day at +6
                    day = data[i + 6] if i + 6 < len(data) and isinstance(data[i + 6], int) and 1 <= data[i + 6] <= 31 else None

                    if day:
                        # Check for NOTE: +16 and +17 contain different values
                        # If both are the same (e.g., both 150='Fysik'), it's a placeholder
                        # If different, one is actual note content
                        v16 = data[i + 16] if i + 16 < len(data) else None
                        v17 = data[i + 17] if i + 17 < len(data) else None

                        has_note = False
                        if isinstance(v16, int) and isinstance(v17, int):
                            # Different values indicate actual content
                            if v16 != v17:
                                has_note = True

                        # Check for HW: +18 or +19 has actual content (not same as placeholder)
                        v18 = data[i + 18] if i + 18 < len(data) else None
                        v19 = data[i + 19] if i + 19 < len(data) else None

                        has_hw = False
                        if isinstance(v18, int) and v18 not in placeholder_indices:
                            has_hw = True
                        if isinstance(v19, int) and v19 not in placeholder_indices:
                            has_hw = True

                        if has_hw:
                            lessons_with_homework.add((lesson_id, day))
                        if has_note:
                            lessons_with_notes.add((lesson_id, day))

                    i += 25  # Skip to next block
                else:
                    i += 1
            else:
                i += 1

        # Known subject names to look for - include ALL subjects including those with special chars
        subject_names = ['Fysik', 'Kemi', 'Dansk', 'Engelsk', 'Matematik', 'Programmering',
                         'SO1', 'SO2', 'SO3', 'SO4', 'SO5', 'IoT', 'CT', 'STAM',
                         'Teknikfag', 'Kommunikation', 'Teknologi',
                         'Studieomr/proj', 'Studieomr']  # Studieomr/proj has a / but is a subject

        # Also detect subjects with special characters (é, etc) by partial matching
        # Include both UTF-8 and encoded versions
        subject_partials = ['Idéhistorie', 'Idéhist', 'IdÃ©', 'Studiecaf', 'studiecaf']

        for i, s in enumerate(strings):
            if not s:
                continue
            # Check exact match first
            if s in subject_names:
                subjects[i] = s
            # Check partial matches for subjects with special chars
            elif any(partial in s for partial in subject_partials):
                # Store the actual string, not the partial
                subjects[i] = s
            elif s and s.islower() and len(s) == 4 and s.isalpha():
                teachers[i] = s
            elif s and len(s) <= 6 and '/' not in s:
                if (s.startswith('M') or s.startswith('L') or s.startswith('N')) and any(c.isdigit() for c in s):
                    rooms[i] = s

        # Build lesson ID to subject/teacher mapping from summary blocks
        # In summary blocks, teacher is at position -1 from lesson_id
        # Subject is around -11 to -12 from lesson_id
        lesson_summaries = {}
        for i in range(len(data)):
            val = data[i]
            if isinstance(val, int) and 400000 < val < 500000:
                lesson_id = val
                if lesson_id in lesson_summaries:
                    continue

                # Teacher is at -1 from lesson_id (data uses 1-based indexing)
                teach = None
                if i >= 1:
                    teacher_idx = data[i - 1]
                    if isinstance(teacher_idx, int) and teacher_idx > 0 and (teacher_idx - 1) in teachers:
                        teach = teachers[teacher_idx - 1]

                # Subject is around -11 to -12 from lesson_id (data uses 1-based indexing)
                subj = None
                for offset in range(-15, -8):
                    if i + offset >= 0:
                        subj_idx = data[i + offset]
                        if isinstance(subj_idx, int) and subj_idx > 0 and (subj_idx - 1) in subjects:
                            subj = subjects[subj_idx - 1]
                            break

                if subj or teach:
                    lesson_summaries[lesson_id] = {'subject': subj, 'teacher': teach}

        lessons = []
        weekday_names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

        # Find class markers once (used for teacher/room detection)
        # Note: GWT uses 1-based string indices, but our parser is 0-based
        # So we need to add 1 to the found index to match data values
        medarbejder_marker = None
        lokaler_marker = None
        for idx, s in enumerate(strings):
            if s and 'MedarbejderISkema' in s:
                medarbejder_marker = idx + 1  # Convert to 1-based for data comparison
            elif s and 'LokalerISkema' in s:
                lokaler_marker = idx + 1  # Convert to 1-based for data comparison

        # FIRST PASS: Find all valid time block positions
        # This prevents searching into adjacent blocks when looking for teacher/room
        time_block_positions = []
        for i in range(len(data) - 50):
            marker = data[i]
            if not (isinstance(marker, int) and -1500 < marker < -100):
                continue
            if i + 1 >= len(data) or data[i + 1] != 0:
                continue
            # Quick validation of time structure
            if i + 18 < len(data):
                start_min = data[i + 2]
                start_hour = data[i + 3]
                day = data[i + 4]
                year_marker = data[i + 6]
                lesson_id = data[i + 18]
                if (isinstance(start_min, int) and 0 <= start_min <= 59 and
                    isinstance(start_hour, int) and 6 <= start_hour <= 20 and
                    isinstance(day, int) and 1 <= day <= 31 and
                    isinstance(year_marker, int) and year_marker in [124, 125, 126, 127] and
                    isinstance(lesson_id, int) and 400000 < lesson_id < 500000):
                    time_block_positions.append(i)

        # SECOND PASS: Process each time block with bounded search ranges
        for block_idx, i in enumerate(time_block_positions):
            marker = data[i]

            try:
                # Extract start time: offset 2=MIN, 3=HOUR, 4=DAY, 6=YEAR
                start_min = data[i + 2]
                start_hour = data[i + 3]
                day = data[i + 4]
                year_marker = data[i + 6]

                # Extract end time: offset 10=MIN, 11=HOUR
                end_min = data[i + 10]
                end_hour = data[i + 11]

                # Validate time values
                if not (isinstance(start_min, int) and 0 <= start_min <= 59):
                    continue
                if not (isinstance(end_min, int) and 0 <= end_min <= 59):
                    continue
                if not (isinstance(start_hour, int) and 6 <= start_hour <= 20):
                    continue
                if not (isinstance(end_hour, int) and 6 <= end_hour <= 20):
                    continue
                if not (isinstance(day, int) and 1 <= day <= 31):
                    continue
                if not (isinstance(year_marker, int) and year_marker in [124, 125, 126, 127]):
                    continue

                # Get subject/lesson_id at offset 17/18
                subject_idx = data[i + 17] if i + 17 < len(data) else None
                lesson_id = data[i + 18] if i + 18 < len(data) else None

                # Validate lesson ID
                if not (isinstance(lesson_id, int) and 400000 < lesson_id < 500000):
                    continue

                # Determine search boundary: stop before next time block starts
                if block_idx + 1 < len(time_block_positions):
                    search_end = time_block_positions[block_idx + 1]
                else:
                    search_end = min(i + 70, len(data))

                # Check for notes - use the pre-computed set from summary blocks
                has_note = (lesson_id, day) in lessons_with_notes

                # Check for homework - use the pre-computed set from summary blocks
                has_homework = (lesson_id, day) in lessons_with_homework

                # Find subject by scanning within the lesson block for known subject indices
                # Subject appears around position 48-65 depending on lesson complexity
                # Start at 45 to skip teacher's subject info (appears at ~32) but catch all subjects
                # Note: data values are 1-based, subjects dict has 0-based keys, so val-1
                subject = ""
                for offset in range(i + 45, min(search_end, len(data))):
                    val = data[offset]
                    if isinstance(val, int) and val > 0 and (val - 1) in subjects:
                        subject = subjects[val - 1]
                        break

                # Fallback: try lesson_summaries
                if not subject and lesson_id in lesson_summaries and lesson_summaries[lesson_id].get('subject'):
                    subject = lesson_summaries[lesson_id].get('subject', '')

                # Get teachers using class marker detection
                # MedarbejderISkema class marker - teacher name is 2 positions BEFORE the marker
                found_teachers = []
                if medarbejder_marker:
                    for offset in range(i + 30, min(search_end, len(data))):
                        if data[offset] == medarbejder_marker:
                            teacher_idx = data[offset - 2] if offset >= 2 else None
                            # Data uses 1-based indexing, teachers dict uses 0-based
                            if isinstance(teacher_idx, int) and teacher_idx > 0 and (teacher_idx - 1) in teachers:
                                t = teachers[teacher_idx - 1]
                                if t not in found_teachers:
                                    found_teachers.append(t)

                teacher = ", ".join(found_teachers) if found_teachers else ""

                # Final fallback: use summary block
                if not teacher and lesson_id in lesson_summaries:
                    teacher = lesson_summaries[lesson_id].get('teacher', '') or ''

                # Get rooms using class marker detection
                # LokalerISkema class marker - room name is 2 positions BEFORE the marker
                found_rooms = []
                if lokaler_marker:
                    for offset in range(i + 35, min(search_end, len(data))):
                        if data[offset] == lokaler_marker:
                            room_idx = data[offset - 2] if offset >= 2 else None
                            # Data uses 1-based indexing, rooms dict uses 0-based
                            if isinstance(room_idx, int) and room_idx > 0 and (room_idx - 1) in rooms:
                                r = rooms[room_idx - 1]
                                if r not in found_rooms:
                                    found_rooms.append(r)

                room = ", ".join(found_rooms) if found_rooms else ""

                # Build date
                actual_year = year_marker + 1900
                lesson_date = None
                for date_str in week_dates:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    if dt.day == day and dt.year == actual_year:
                        lesson_date = date_str
                        break

                if not lesson_date:
                    lesson_date = f"{actual_year}-{month:02d}-{day:02d}"

                # Get weekday
                try:
                    dt = datetime.strptime(lesson_date, '%Y-%m-%d')
                    weekday = weekday_names[dt.weekday()]
                except:
                    weekday = "Unknown"

                # Format time
                time_str = f"{start_hour:02d}:{start_min:02d}-{end_hour:02d}:{end_min:02d}"

                lesson = {
                    'id': f"{lesson_date}_{start_hour:02d}:{start_min:02d}",
                    'date': lesson_date,
                    'weekday': weekday,
                    'time': time_str,
                    'subject': subject or "",
                    'teacher': teacher or "",
                    'room': room or "",
                    'has_homework': has_homework,
                    'has_note': has_note,
                    'has_files': False
                }

                # Avoid duplicates
                if not any(l['id'] == lesson['id'] and l['subject'] == lesson['subject'] for l in lessons):
                    lessons.append(lesson)

            except (IndexError, TypeError, ValueError):
                continue

        # Sort by date and time
        lessons.sort(key=lambda x: (x['date'], x['time']))

        # Only keep HW/NOTE flags on the FIRST lesson of each consecutive group
        # (same subject on same date in consecutive time slots)
        prev_date = None
        prev_subject = None
        prev_had_hw = False
        prev_had_note = False

        for lesson in lessons:
            curr_date = lesson['date']
            curr_subject = lesson['subject']

            # Check if this is a continuation of the previous lesson group
            same_group = (curr_date == prev_date and curr_subject == prev_subject)

            if same_group:
                # This is a continuation - remove flags if the first one had them
                if prev_had_hw:
                    lesson['has_homework'] = False
                if prev_had_note:
                    lesson['has_note'] = False
            else:
                # New group - track if this first lesson has flags
                prev_had_hw = lesson.get('has_homework', False)
                prev_had_note = lesson.get('has_note', False)

            prev_date = curr_date
            prev_subject = curr_subject

        return lessons

    async def get_schedule_homework(self) -> List[Dict]:
        """Get homework from schedule (compatibility method)."""
        lessons, _, _, _ = await self.parse_schedule(0)
        return [l for l in lessons if l.get('has_homework') or l.get('has_note')]

    # ============================================================
    # HOMEWORK/NOTES API
    # ============================================================

    def get_homework_messages_raw(self, start_date: datetime = None, end_date: datetime = None) -> str:
        """Get raw homework messages via GWT-RPC."""
        if not self.login():
            raise Exception("Login failed")

        if start_date is None:
            start_date = datetime.now()
        if end_date is None:
            end_date = start_date + timedelta(days=6)

        payload = (
            "7|0|6|"
            f"{self.base_url}/skema/skema/|"
            "366DFB19BE92393600809C88D33DD15A|"
            "dk.uddata.services.interfaces.AktivitetskalenderService|"
            "hentAlleMineBeskeder|"
            "dk.uddata.gwt.comm.shared.UDate/2314285719|"
            "UDate:|"
            "1|2|3|4|2|5|5|"
            f"{self._encode_date(start_date)}"
            f"{self._encode_date(end_date)}"
        )

        return self._make_gwt_call(
            f"{self.base_url}/skema/aktivitetskalenderservice",
            payload,
            self.skema_permutation,
            "skema"
        )

    # ============================================================
    # ASSIGNMENTS API
    # ============================================================

    def get_assignments_raw(self) -> str:
        """Get raw assignments via GWT-RPC."""
        if not self.login():
            raise Exception("Login failed")

        payload = (
            "7|0|4|"
            f"{self.base_url}/opgave/opgave/|"
            "459B74E0E07134BC40784E117D837355|"
            "dk.uddata.services.interfaces.OpgaveService|"
            "getAlleAfleveringer|"
            "1|2|3|4|0|"
        )

        return self._make_gwt_call(
            f"{self.base_url}/opgave/opgaveservice",
            payload,
            self.opgave_permutation,
            "opgave"
        )

    def get_aflevering_raw(self, aflevering_id: int) -> str:
        """
        Get raw single assignment details via GWT-RPC getAflevering.

        Args:
            aflevering_id: The assignment ID (from OpgaveElev, not Aflevering)

        Returns:
            Raw GWT-RPC response string
        """
        if not self.login():
            raise Exception("Login failed")

        # GWT-RPC payload for getAflevering(int afleveringId)
        payload = (
            "7|0|5|"
            f"{self.base_url}/opgave/opgave/|"
            "459B74E0E07134BC40784E117D837355|"
            "dk.uddata.services.interfaces.OpgaveService|"
            "getAflevering|"
            "I|"
            f"1|2|3|4|1|5|{aflevering_id}|"
        )

        return self._make_gwt_call(
            f"{self.base_url}/opgave/opgaveservice",
            payload,
            self.opgave_permutation,
            "opgave"
        )

    def get_assignment_files(self, container_id: int) -> List[Dict]:
        """
        Get files attached to an assignment via ressourceservice.

        Uses the same RessourceService as lesson files but with type 5 (OPGAVE)
        instead of type 12 (SKEMA).

        Args:
            container_id: The container ID from Aflevering (field c)

        Returns:
            List of file dicts: [{'name': str, 'id': int, 'uuid': str}, ...]
        """
        if not self.login():
            return []

        # GWT-RPC payload for findRessourcerPerContainer
        # Type 5 = OPGAVE (assignment), Type 12 = SKEMA (lesson)
        payload = (
            "7|0|6|"
            f"{self.base_url}/opgave/opgave/|"
            "09D4724C79CC98B839803FCB9CBF2218|"
            "dk.uddata.services.interfaces.RessourceService|"
            "findRessourcerPerContainer|"
            "dk.uddata.model.ressourcer.RessourceKey/785242658|"
            "dk.uddata.model.ressourcer.RessourceObjektType/3745084519|"
            f"1|2|3|4|1|5|5|{container_id}|6|5|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/opgave/ressourceservice",
                payload,
                self.opgave_permutation,
                "opgave"
            )

            if response.startswith('//OK'):
                return self._parse_ressource_response(response)
            else:
                logger.debug(f"Assignment files fetch failed for container_id={container_id}: {response[:200]}")
                return []
        except Exception as e:
            logger.debug(f"Error fetching assignment files for container_id={container_id}: {e}")
            return []

    async def get_lesson_details(self, date: str, time: str) -> Dict:
        """Get details for a specific lesson."""
        lessons, _, _, _ = await self.parse_schedule(0)

        for lesson in lessons:
            if lesson['date'] == date and lesson['time'] == time:
                return lesson

        return {'error': f'Lesson not found at {date} {time}'}

    # ============================================================
    # ASSIGNMENTS (stub implementations)
    # ============================================================

    async def get_homework(self, only_open: bool = True) -> List[Dict]:
        """
        Get assignments from GWT-RPC API using proper GWT deserializer.

        Args:
            only_open: If True, only return non-submitted assignments

        Returns list of assignments with subject, title, deadline, etc.
        """
        try:
            response = self.get_assignments_raw()
            deserializer = GWTDeserializer(response)
            assignments = deserializer.parse_assignments(only_open=only_open)

            # Add row_index for compatibility
            for i, a in enumerate(assignments):
                a['row_index'] = str(i)

            logger.info(f"Found {len(assignments)} assignments via GWT deserializer (only_open={only_open})")
            return assignments

        except Exception as e:
            logger.error(f"Error fetching assignments: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_assignment_details(self, row_index: str) -> Dict:
        """
        Get assignment details by row index.

        Returns assignment info including description (HTML content) and files.
        Uses getAflevering GWT-RPC call for full details.
        """
        try:
            # Get all assignments to find the one at row_index
            assignments = await self.get_homework(only_open=False)
            idx = int(row_index)

            if not (0 <= idx < len(assignments)):
                return {'error': f'Assignment not found at index {row_index}'}

            assignment = assignments[idx]
            container_id = assignment.get('container_id')

            # Get files for this assignment using container_id
            files = []
            if container_id:
                files = self.get_assignment_files(container_id)
                logger.info(f"Found {len(files)} files for assignment with container_id={container_id}")

            return {
                'assignment_title': assignment.get('title', ''),
                'subject': assignment.get('subject', ''),
                'description': assignment.get('description', ''),
                'student_time': assignment.get('hours_spent', ''),
                'responsible': '',
                'course': assignment.get('class', ''),
                'evaluation_form': '',
                'groups': '',
                'submission_status': 'Afleveret' if assignment.get('submitted') else 'Ikke afleveret',
                'deadline': assignment.get('deadline', ''),
                'files': files,
                'row_index': row_index,
                'container_id': container_id,
            }

        except Exception as e:
            logger.error(f"Error getting assignment details: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    async def download_lesson_file(self, file_url: str, file_name: str, output_dir: str = "./downloads") -> Dict:
        """
        Download a file from a lesson.
        """
        import os

        try:
            if not self.login():
                return {'success': False, 'error': 'Login failed'}

            os.makedirs(output_dir, exist_ok=True)
            response = self.session.get(file_url, stream=True)

            if response.status_code == 200:
                file_path = os.path.join(output_dir, file_name)
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                return {
                    'success': True,
                    'file_path': file_path,
                    'file_name': file_name,
                    'file_size': os.path.getsize(file_path)
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def load_lesson_file(self, file_url: str, file_name: str) -> Dict:
        """
        Load a file and return its content.
        """
        import base64
        import mimetypes

        try:
            if not self.login():
                return {'success': False, 'error': 'Login failed'}

            response = self.session.get(file_url)

            if response.status_code == 200:
                content_type = response.headers.get('content-type', 'application/octet-stream')
                is_text = content_type.startswith('text/') or content_type == 'application/json'

                if is_text:
                    content = response.text
                else:
                    content = base64.b64encode(response.content).decode('utf-8')

                return {
                    'success': True,
                    'file_name': file_name,
                    'content': content,
                    'content_type': content_type,
                    'size': len(response.content),
                    'is_text': is_text
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================
    # CONTEXT MANAGER SUPPORT (for compatibility with Playwright)
    # ============================================================

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    async def start(self):
        """Start method for compatibility."""
        pass

    async def close(self):
        """Close method for compatibility."""
        pass


async def main():
    """Test the requests scraper."""
    scraper = StudiePlusRequestsScraper()

    logger.info("Testing requests-based scraper...")
    logger.info(f"School: {scraper.school}")
    logger.info(f"Username: {scraper.username}")

    if not scraper.login():
        logger.error("Login failed!")
        return

    logger.info("\n=== SCHEDULE (current offset-based method) ===")
    lessons, week_number, year, dates = await scraper.parse_schedule(0)
    logger.info(f"Week: {week_number}/{year}")
    logger.info(f"Dates: {dates}")
    logger.info(f"Found {len(lessons)} lessons")

    for lesson in lessons[:15]:
        logger.info(f"  {lesson['date']} {lesson['time']} - {lesson['subject']} ({lesson['teacher']}) @ {lesson['room']}")

    # Test the GWT deserializer
    logger.info("\n=== TESTING GWT DESERIALIZER ===")
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    raw_response = scraper.get_schedule_raw(start_of_week, start_of_week + timedelta(days=6))

    try:
        parser = GWTScheduleParser(raw_response)
        logger.info(f"Parser initialized:")
        logger.info(f"  Data length: {len(parser.data)}")
        logger.info(f"  String table length: {len(parser.strings)}")

        # Show class markers found
        logger.info("\n=== CLASS MARKERS FOUND ===")
        logger.info(f"  SkemaBegivenhed: {parser.SKEMA_BEGIVENHED}")
        logger.info(f"  LokalerISkema: {parser.LOKALER_I_SKEMA}")
        logger.info(f"  MedarbejderISkema: {parser.MEDARBEJDER_I_SKEMA}")

        # Parse lessons using the deserializer
        logger.info("\n=== PARSED LESSONS ===")
        gwt_lessons = parser.parse_lessons()
        logger.info(f"Found {len(gwt_lessons)} lessons via deserializer")
        for lesson in gwt_lessons[:15]:
            logger.info(f"  {lesson}")

    except Exception as e:
        logger.error(f"Deserializer error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
