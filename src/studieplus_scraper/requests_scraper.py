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
from .gwt_deserializer import parse_schedule_response, GWTDeserializer

load_dotenv()


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

        # GWT hashes are discovered automatically from StudiePlus JavaScript
        self.skema_permutation = None
        self.opgave_permutation = None
        self._service_hashes = {}  # module -> {servicename: hash}

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

    def _discover_gwt_hashes(self, module: str) -> Tuple[str, Dict[str, str]]:
        """
        Auto-discover GWT permutation hash and service hashes for a module.

        Fetches {module}.nocache.js to find the webkit permutation hash,
        then fetches the cache.js to extract service hashes.

        Returns: (permutation_hash, {service_name: service_hash})
        """
        nocache_url = f"{self.base_url}/{module}/{module}/{module}.nocache.js"
        resp = self.session.get(nocache_url)

        if resp.status_code != 200:
            raise Exception(f"Could not fetch {nocache_url}")

        # nocache.js assigns hashes to variables, then maps them to browser+locale combos
        # The webkit hash is the first one assigned (mapped to 'webkit')
        # Pattern: variable='HASH' where variables are assigned in order
        hashes = re.findall(r"='([A-F0-9]{32})'", resp.text)
        if not hashes:
            raise Exception(f"No permutation hashes found in {module}.nocache.js")

        # First hash is always webkit (Chrome/Edge/etc.)
        perm_hash = hashes[0]
        logger.info(f"Discovered {module} permutation hash: {perm_hash}")

        # Fetch the cache.js to find service hashes
        cache_url = f"{self.base_url}/{module}/{module}/{perm_hash}.cache.js"
        cache_resp = self.session.get(cache_url)

        if cache_resp.status_code != 200:
            raise Exception(f"Could not fetch {cache_url}")

        # Service hashes follow pattern: FuncName.call(this,Func(),'servicename','HASH',...)
        # The function name is minified and varies between modules
        service_matches = re.findall(
            r",'(\w+service)','([A-F0-9]{32})'",
            cache_resp.text
        )

        service_hashes = {name: hash_val for name, hash_val in service_matches}
        logger.info(f"Discovered {module} service hashes: {list(service_hashes.keys())}")

        return perm_hash, service_hashes

    def _ensure_hashes(self, module: str):
        """Ensure GWT hashes are discovered for the given module."""
        if module == "skema" and self.skema_permutation:
            return
        if module == "opgave" and self.opgave_permutation:
            return

        perm_hash, service_hashes = self._discover_gwt_hashes(module)
        self._service_hashes[module] = service_hashes

        if module == "skema":
            self.skema_permutation = perm_hash
        elif module == "opgave":
            self.opgave_permutation = perm_hash

    def _get_service_hash(self, module: str, service_name: str) -> str:
        """Get the serialization policy hash for a GWT service."""
        self._ensure_hashes(module)
        hashes = self._service_hashes.get(module, {})
        if service_name not in hashes:
            raise Exception(f"Service '{service_name}' not found in {module} module. Available: {list(hashes.keys())}")
        return hashes[service_name]

    def login(self) -> bool:
        """Login to StudiePlus."""
        if self.logged_in:
            return True

        if not self.username or not self.password or not self.school:
            missing = []
            if not self.username:
                missing.append("STUDIEPLUS_USERNAME")
            if not self.password:
                missing.append("STUDIEPLUS_PASSWORD")
            if not self.school:
                missing.append("STUDIEPLUS_SCHOOL")
            raise Exception(f"Manglende login-oplysninger: {', '.join(missing)} skal sættes som environment variables")

        try:
            instnr = self._find_school_instnr()
            if not instnr:
                raise Exception(f"Skolen '{self.school}' blev ikke fundet. Tjek STUDIEPLUS_SCHOOL environment variable.")

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
            raise Exception("Login fejlede - tjek brugernavn og adgangskode (STUDIEPLUS_USERNAME og STUDIEPLUS_PASSWORD)")

        except Exception as e:
            if "Manglende login" in str(e) or "ikke fundet" in str(e) or "Login fejlede" in str(e):
                raise
            logger.error(f"Login error: {e}")
            raise Exception(f"Login fejl: {e}")

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

    def get_note_file_container(self, lesson_id: int) -> Optional[int]:
        """
        Get the file container_id for a lesson by calling hentNoteForSkema.

        The schedule's SkemaNote2.c is NOT the file container — we need to call
        hentNoteForSkema(lesson_id) to get the Note which contains the actual
        file container_id in its nested SkemaNote2.
        """
        if not self.login():
            return None

        skemanote_hash = self._get_service_hash("skema", "skemanoteservice")
        if not skemanote_hash:
            return None

        payload = (
            "7|0|5|"
            f"{self.base_url}/skema/skema/|"
            f"{skemanote_hash}|"
            "dk.uddata.services.interfaces.SkemaNote2Service|"
            "hentNoteForSkema|"
            "I|"
            f"1|2|3|4|1|5|{lesson_id}|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/skema/skemanoteservice",
                payload,
                self.skema_permutation,
                "skema"
            )

            if not response.startswith('//OK'):
                return None

            deserializer = GWTDeserializer(response)
            note = deserializer._read_object()

            if not isinstance(note, dict) or note.get('_class') != 'Note':
                logger.debug(f"Expected Note object, got: {type(note)}")
                return None

            skema_note2 = note.get('skema_note2')
            if not isinstance(skema_note2, dict):
                logger.debug(f"No SkemaNote2 in Note response")
                return None

            container_id = skema_note2.get('file_container_id')
            if isinstance(container_id, int) and container_id > 0:
                logger.info(f"Found file container_id={container_id} for lesson_id={lesson_id}")
                return container_id

            return None

        except Exception as e:
            logger.debug(f"Error getting note for lesson_id={lesson_id}: {e}")
            return None

    def get_lesson_files(self, container_id: int) -> List[Dict]:
        """
        Get files attached to a lesson via ressourceservice.findRessourcerPerContainer.

        Args:
            container_id: The file container_id (from get_note_file_container)
        """
        if not self.login():
            return []

        ressource_hash = self._get_service_hash("skema", "ressourceservice")
        payload = (
            "7|0|6|"
            f"{self.base_url}/skema/skema/|"
            f"{ressource_hash}|"
            "dk.uddata.services.interfaces.RessourceService|"
            "findRessourcerPerContainer|"
            "dk.uddata.model.ressourcer.RessourceKey/785242658|"
            "dk.uddata.model.ressourcer.RessourceObjektType/3745084519|"
            f"1|2|3|4|1|5|5|{container_id}|6|12|"
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
                logger.debug(f"Ressource fetch failed for container_id={container_id}: {response[:200]}")
                return []
        except Exception as e:
            logger.debug(f"Error fetching ressources for container_id={container_id}: {e}")
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

    def _parse_url_response(self, response: str) -> Optional[str]:
        """Extract signed URL from a hentRessourceUrl/hentRessourceUrlText response."""
        if not response.startswith('//OK'):
            return None
        try:
            parsed = json.loads(response[4:])
            if len(parsed) > 1 and isinstance(parsed[1], list) and len(parsed[1]) > 0:
                return parsed[1][0]
        except Exception:
            pass
        return None

    def get_file_download_url(self, file_id: int, is_skemanote: bool = False) -> Optional[str]:
        """
        Get the signed download URL for a file.

        Assignment files use hentRessourceUrl(int, String) via opgave module.
        Schedule note files use hentRessourceUrlText(int) via skema module.

        Args:
            file_id: The ressource/file ID
            is_skemanote: True for schedule note files (uses hentRessourceUrlText)
        """
        if not self.login():
            return None

        if is_skemanote:
            url = self._get_url_via_text(file_id)
            if url:
                return url
            url = self._get_url_via_standard(file_id, "skema")
            if url:
                return url
        else:
            url = self._get_url_via_standard(file_id, "opgave")
            if url:
                return url
            url = self._get_url_via_text(file_id)
            if url:
                return url

        logger.debug(f"hentRessourceUrl failed for file_id={file_id}")
        return None

    def _get_url_via_text(self, file_id: int) -> Optional[str]:
        """Call hentRessourceUrlText(int) — used for schedule note files."""
        hash_val = self._get_service_hash("skema", "ressourceservice")
        if not hash_val:
            return None

        payload = (
            "7|0|5|"
            f"{self.base_url}/skema/skema/|"
            f"{hash_val}|"
            "dk.uddata.services.interfaces.RessourceService|"
            "hentRessourceUrlText|"
            "I|"
            f"1|2|3|4|1|5|{file_id}|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/skema/ressourceservice",
                payload,
                self.skema_permutation,
                "skema"
            )
            return self._parse_url_response(response)
        except Exception:
            return None

    def _get_url_via_standard(self, file_id: int, module: str) -> Optional[str]:
        """Call hentRessourceUrl(int, String) — used for assignment/regular files."""
        if module == "opgave":
            hash_val = self._get_service_hash("opgave", "ressourceservice")
            perm = self.opgave_permutation
        else:
            hash_val = self._get_service_hash("skema", "ressourceservice")
            perm = self.skema_permutation

        if not hash_val:
            return None

        payload = (
            "7|0|7|"
            f"{self.base_url}/{module}/{module}/|"
            f"{hash_val}|"
            "dk.uddata.services.interfaces.RessourceService|"
            "hentRessourceUrl|"
            "I|"
            "java.lang.String/2004016611|"
            "|"
            f"1|2|3|4|2|5|6|{file_id}|7|"
        )

        try:
            response = self._make_gwt_call(
                f"{self.base_url}/{module}/ressourceservice",
                payload,
                perm,
                module
            )
            return self._parse_url_response(response)
        except Exception:
            return None

    def get_lesson_files_with_urls(self, lesson_id: int) -> List[Dict]:
        """
        Get files for a lesson with download URLs.

        Full flow (matching the website):
        1. hentNoteForSkema(lesson_id) → get file container_id
        2. findRessourcerPerContainer(container_id, SKEMANOTE) → get files
        3. hentRessourceUrl(fileId, "") → get signed S3 URLs

        Args:
            lesson_id: The lesson/skema event ID
        """
        file_container_id = self.get_note_file_container(lesson_id)
        if not file_container_id:
            logger.debug(f"No file container found for lesson_id={lesson_id}")
            return []

        files = self.get_lesson_files(file_container_id)

        for f in files:
            if f.get('id'):
                url = self._get_url_via_standard(f['id'], "skema")
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
        note_hash = self._get_service_hash("skema", "skemanoteservice")
        payload = (
            "7|0|5|"
            f"{self.base_url}/skema/skema/|"
            f"{note_hash}|"
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
        self.login()

        if start_date is None:
            start_date = datetime.now()
        if end_date is None:
            end_date = start_date + timedelta(days=6)

        skema_hash = self._get_service_hash("skema", "skemaservice")
        payload = (
            "7|0|6|"
            f"{self.base_url}/skema/skema/|"
            f"{skema_hash}|"
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
            if gl.end_time:
                time_str = f"{gl.start_time.strftime('%H:%M')}-{gl.end_time.strftime('%H:%M')}"
            else:
                time_str = gl.start_time.strftime('%H:%M')
            weekday = weekday_names[gl.start_time.weekday()]

            lesson = {
                'id': f"{lesson_date}_{gl.start_time.strftime('%H:%M')}",
                'lesson_id': gl.lesson_id,
                'file_container_id': gl.file_container_id,
                'date': lesson_date,
                'weekday': weekday,
                'time': time_str,
                'subject': gl.subject or "",
                'teacher': ", ".join(gl.teachers) if gl.teachers else "",
                'room': ", ".join(gl.rooms) if gl.rooms else "",
                'has_homework': gl.has_homework,
                'has_note': gl.has_note,
                'has_files': gl.has_files,
                'homework': gl.homework or "",
                'note': gl.note or "",
            }
            lessons.append(lesson)

        # Sort by date and time
        lessons.sort(key=lambda x: (x['date'], x['time']))

        return (lessons, week_number, year, dates)

    async def get_schedule_homework(self) -> List[Dict]:
        """Get homework from schedule (compatibility method)."""
        lessons, _, _, _ = await self.parse_schedule(0)
        return [l for l in lessons if l.get('has_homework') or l.get('has_note')]

    # ============================================================
    # HOMEWORK/NOTES API
    # ============================================================

    def get_homework_messages_raw(self, start_date: datetime = None, end_date: datetime = None) -> str:
        """Get raw homework messages via GWT-RPC."""
        self.login()

        if start_date is None:
            start_date = datetime.now()
        if end_date is None:
            end_date = start_date + timedelta(days=6)

        aktivitet_hash = self._service_hashes.get("skema", {}).get("aktivitetskalenderservice")
        if not aktivitet_hash:
            raise Exception("AktivitetskalenderService is no longer available in StudiePlus")
        payload = (
            "7|0|6|"
            f"{self.base_url}/skema/skema/|"
            f"{aktivitet_hash}|"
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
        self.login()

        opgave_hash = self._get_service_hash("opgave", "opgaveservice")
        payload = (
            "7|0|4|"
            f"{self.base_url}/opgave/opgave/|"
            f"{opgave_hash}|"
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
        self.login()

        # GWT-RPC payload for getAflevering(int afleveringId)
        opgave_hash = self._get_service_hash("opgave", "opgaveservice")
        payload = (
            "7|0|5|"
            f"{self.base_url}/opgave/opgave/|"
            f"{opgave_hash}|"
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
        ressource_hash = self._get_service_hash("opgave", "ressourceservice")
        payload = (
            "7|0|6|"
            f"{self.base_url}/opgave/opgave/|"
            f"{ressource_hash}|"
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
        response = self.get_assignments_raw()

        try:
            deserializer = GWTDeserializer(response)
            assignments = deserializer.parse_assignments(only_open=only_open)

            # Add id (using container_id) for fetching details later
            for a in assignments:
                a['id'] = str(a.get('container_id', ''))

            logger.info(f"Found {len(assignments)} assignments via GWT deserializer (only_open={only_open})")
            return assignments

        except Exception as e:
            logger.error(f"Error parsing assignments: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_assignment_details(self, assignment_id: str) -> Dict:
        """
        Get assignment details by id (container_id).

        Returns assignment info including description (HTML content) and files.
        Uses getAflevering GWT-RPC call for full details.
        """
        try:
            # Get all assignments and find the one with matching container_id
            assignments = await self.get_homework(only_open=False)

            # Find assignment by container_id
            assignment = None
            for a in assignments:
                if str(a.get('container_id')) == assignment_id:
                    assignment = a
                    break

            if not assignment:
                return {'error': f'Assignment not found with id {assignment_id}'}

            container_id = assignment.get('container_id')
            teacher_container_id = assignment.get('teacher_file_container_id')

            # Two separate ressource containers:
            # - teacher_file_container_id (OpgaveElev.t): teacher-attached materials (bId in JS)
            # - container_id (Aflevering.d): student's submitted files (dId in JS)
            files = []

            if teacher_container_id:
                teacher_files = self.get_assignment_files(teacher_container_id)
                for f in teacher_files:
                    f['source'] = 'teacher'
                files.extend(teacher_files)
                logger.info(f"Found {len(teacher_files)} teacher files for teacher_container_id={teacher_container_id}")

            if container_id:
                student_files = self.get_assignment_files(container_id)
                for f in student_files:
                    f['source'] = 'student'
                files.extend(student_files)
                logger.info(f"Found {len(student_files)} student files for container_id={container_id}")

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
                'id': str(container_id),
            }

        except Exception as e:
            logger.error(f"Error getting assignment details: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    async def download_lesson_file(self, file_url: str, file_name: str, output_dir: str = None) -> Dict:
        """
        Download a file from a lesson to the user's computer.
        """
        import os
        from pathlib import Path

        try:
            if not self.login():
                return {'success': False, 'error': 'Login failed'}

            if output_dir is None:
                output_dir = str(Path.home() / "Downloads")

            output_dir = str(Path(output_dir).resolve())
            os.makedirs(output_dir, exist_ok=True)

            response = self.session.get(file_url, stream=True)

            if response.status_code == 200:
                file_path = os.path.join(output_dir, file_name)
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                return {
                    'success': True,
                    'file_path': str(Path(file_path).resolve()),
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
        parser = GWTDeserializer(raw_response)
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
