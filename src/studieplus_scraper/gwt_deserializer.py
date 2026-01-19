"""
GWT-RPC Response Deserializer for StudiePlus

Stack-based deserializer that mirrors the JavaScript implementation.
See CLAUDE.md for detailed documentation of the format.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SkemaLesson:
    """Parsed lesson from GWT response."""
    lesson_id: int = 0
    subject: str = ""
    teachers: List[str] = field(default_factory=list)
    rooms: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    note: str = ""
    has_homework: bool = False
    has_note: bool = False
    has_files: bool = False

    def __repr__(self):
        time_str = ""
        if self.start_time and self.end_time:
            time_str = f"{self.start_time.strftime('%Y-%m-%d %H:%M')}-{self.end_time.strftime('%H:%M')}"
        teachers = ", ".join(self.teachers) if self.teachers else "?"
        rooms = ", ".join(self.rooms) if self.rooms else "?"
        return f"Lesson({self.subject} {time_str} | {teachers} @ {rooms})"


class GWTDeserializer:
    """
    Stack-based GWT-RPC deserializer.

    Mirrors the JavaScript implementation:
    - a.b = data array
    - a.a = stack pointer (decrements on read)
    - a.d = string table (1-based indexing)
    - a.e = object cache (for back-references)
    """

    def __init__(self, response: str):
        self.raw = response
        self.data: List[Any] = []       # a.b in JS
        self.pos: int = 0               # a.a in JS (stack pointer)
        self.strings: List[str] = []    # a.d in JS
        self.objects: List[Any] = []    # a.e in JS (object cache)

        self._deserializers: Dict[str, Callable] = {}
        self._register_deserializers()
        self._parse_response()

    def _register_deserializers(self):
        """Register deserializers for known class types."""
        self._deserializers = {
            # Java standard types
            'java.util.ArrayList': self._deserialize_arraylist,
            'java.util.HashMap': self._deserialize_hashmap,
            'java.lang.Integer': self._deserialize_integer,
            'java.lang.Boolean': self._deserialize_boolean_obj,

            # GWT types
            'dk.uddata.gwt.comm.shared.UDate': self._deserialize_udate,

            # Main data types
            'dk.uddata.model.skema.PersSkemaData': self._deserialize_pers_skema_data,
            'dk.uddata.model.skema.SkemaBegivenhed': self._deserialize_skema_begivenhed,
            'dk.uddata.model.skema.SkemaBegivenhed$LokalerISkema': self._deserialize_lokaler,
            'dk.uddata.model.skema.SkemaBegivenhed$MedarbejderISkema': self._deserialize_medarbejder,
            'dk.uddata.model.skema.SkemaBegivenhed$AktiviteterISkema': self._deserialize_aktiviteter,
            'dk.uddata.model.skema.SkemaBegivenhed$Status': self._deserialize_enum,
            'dk.uddata.model.skemanoter.SkemaNote2': self._deserialize_skema_note,

            # Aarstyp types (p4f: a=405, b=24, c=int, d=519, e=string, f=311)
            'dk.uddata.model.skema.Aarstyp': self._deserialize_aarstyp,
            'dk.uddata.model.skema.Aarstyp$AarsagsType': self._deserialize_enum,
            'dk.uddata.model.skema.Aarstyp$AmuKode': self._deserialize_enum,
            'dk.uddata.model.skema.Aarstyp$Status': self._deserialize_enum,

            # Frareg types
            'dk.uddata.model.skema.Frareg': self._deserialize_frareg,
            'dk.uddata.model.skema.Frareg$Status': self._deserialize_enum,

            # Fravk types
            'dk.uddata.model.skema.Fravk': self._deserialize_fravk,
            'dk.uddata.model.skema.Fravk$FravkStatus': self._deserialize_enum,

            # Other types
            'dk.uddata.model.bruger.Skemaelev': self._deserialize_skemaelev,
            'dk.uddata.model.skema.SkemaUvfo': self._deserialize_skema_uvfo,
            'dk.uddata.model.skema.SkemaTools$FravaStatus': self._deserialize_enum,
            'dk.uddata.model.skema.SkemaTools$RegModel': self._deserialize_enum,
            'dk.uddata.model.skema.SkemaTools$RegStatus': self._deserialize_enum,
        }

    def _parse_response(self):
        """Parse GWT response into data array and string table."""
        content = self.raw.strip()

        if content.startswith("//OK"):
            content = content[4:]
        elif content.startswith("//EX"):
            raise ValueError(f"GWT Exception: {content}")

        parsed = json.loads(content)

        # GWT-RPC format: [data..., ["strings"], flags, version]
        # String table is at index -3, flags at -2, version at -1
        if len(parsed) < 3:
            raise ValueError("Response too short")

        if not isinstance(parsed[-3], list):
            raise ValueError("Could not find string table at expected position")

        self.strings = parsed[-3]
        # Data is everything before string table
        self.data = parsed[:-3]
        # Stack pointer starts at end of data (read backwards)
        self.pos = len(self.data)

    def _pop(self, debug: bool = False) -> Any:
        """Pop a value from the stack (a.b[--a.a] in JS)."""
        self.pos -= 1
        if self.pos < 0:
            raise ValueError("Stack underflow")
        val = self.data[self.pos]
        if debug:
            str_hint = ""
            if isinstance(val, int) and 0 < val <= len(self.strings):
                str_hint = f" = {self.strings[val-1][:40]}"
            print(f"  POP [{self.pos}] = {val}{str_hint}")
        return val

    def _peek(self, offset: int = 0) -> Any:
        """Peek at a value without popping."""
        idx = self.pos - 1 - offset
        if idx < 0:
            return None
        return self.data[idx]

    def _read_string(self) -> Optional[str]:
        """
        Read a string using pqd pattern (SINGLE pop):
        val = a.b[--a.a]; return val > 0 ? a.d[val - 1] : null

        Note: The babel-inlined JS had a bug that looked like TWO pops,
        but the original source_clean.js shows it's a SINGLE pop.
        """
        val = self._pop()
        if val > 0 and val <= len(self.strings):
            return self.strings[val - 1]
        return None

    def _read_bool(self) -> bool:
        """Read a boolean (!!a.b[--a.a] in JS)."""
        return bool(self._pop())

    def _is_class_marker(self, s: str) -> bool:
        """Check if a string is a GWT class marker (package.Class/hash)."""
        if '/' not in s:
            return False
        # Class markers have format: dk.uddata.model.skema.ClassName/123456
        parts = s.split('/')
        if len(parts) != 2:
            return False
        # Class part should have dots (package structure)
        class_part = parts[0]
        if '.' not in class_part:
            return False
        # Hash part should be numeric
        try:
            int(parts[1])
            return True
        except ValueError:
            return False

    def _read_object(self) -> Any:
        """
        Read an object using iqd pattern.

        b = a.b[--a.a]
        if (b < 0) return a.e[-(b + 1)]  // back-reference
        c = b > 0 ? a.d[b - 1] : null    // class string
        if (c == null) return null
        // deserialize and cache
        """
        b = self._pop()

        if b < 0:
            # Back-reference to previously deserialized object
            idx = -(b + 1)
            if 0 <= idx < len(self.objects):
                return self.objects[idx]
            return None

        if b == 0:
            return None

        # Get class string from string table (1-based)
        if b > len(self.strings):
            return None
        class_str = self.strings[b - 1]

        # Only treat as class marker if it has proper format (package.Class/hash)
        if not self._is_class_marker(class_str):
            # Not a class marker - this is unexpected, return raw value
            return b

        # Find deserializer by matching class name prefix (most specific match wins)
        deserializer = None
        best_match = ""
        for class_prefix, func in self._deserializers.items():
            if class_str.startswith(class_prefix) and len(class_prefix) > len(best_match):
                deserializer = func
                best_match = class_prefix

        # if deserializer:
        #     print(f"DEBUG _read_object: class={class_str[:50]}, deserializer={best_match}, pos={self.pos}")

        if deserializer is None:
            # Unknown type - create placeholder and skip
            obj = {'_class': class_str, '_unknown': True}
            self.objects.append(obj)
            return obj

        # Reserve slot in object cache before deserializing
        obj_idx = len(self.objects)
        self.objects.append(None)

        # Deserialize
        try:
            obj = deserializer()
        except Exception as e:
            print(f"ERROR deserializing {class_str}: {e} at pos={self.pos}")
            obj = {'_class': class_str, '_error': str(e)}
        self.objects[obj_idx] = obj

        return obj

    def _deserialize_arraylist(self) -> List[Any]:
        """
        Deserialize ArrayList (Fod function).

        e = a.b[--a.a]  // count
        for (c = 0; c < e; ++c) {
            d = iqd(a)  // read element
            list.add(d)
        }
        """
        count = self._pop()
        result = []
        for _ in range(count):
            item = self._read_object()
            result.append(item)
        return result

    def _deserialize_hashmap(self, debug: bool = False) -> dict:
        """Deserialize HashMap - just read count and key/value pairs."""
        count = self._pop()
        if debug:
            print(f"DEBUG HashMap: count={count}, pos={self.pos}")
        result = {}
        for i in range(count):
            key = self._read_object()
            value = self._read_object()
            if debug and i < 3:
                print(f"DEBUG HashMap pair {i}: key={key}, value={value}")
            if key is not None:
                result[str(key)] = value
        return result

    def _deserialize_integer(self) -> int:
        """Deserialize Integer wrapper."""
        return self._pop()

    def _deserialize_boolean_obj(self) -> bool:
        """Deserialize Boolean wrapper."""
        return self._read_bool()

    def _deserialize_pers_skema_data(self, debug: bool = False) -> dict:
        """
        Deserialize PersSkemaData (Wlg function).

        This is the top-level response object.
        Field b.d contains the list of SkemaBegivenhed.
        """
        if debug:
            print(f"DEBUG PersSkemaData: ENTER pos={self.pos}")
            print(f"DEBUG: Stack preview: {self.data[self.pos-10:self.pos]}")

        # b.a = type 29
        pos_before_a = self.pos
        a = self._read_object()
        if debug:
            print(f"DEBUG: b.a read from {pos_before_a} (value={self.data[pos_before_a-1] if pos_before_a > 0 else 'N/A'}), now pos={self.pos}")

        # b.b = UDate (type 7)
        pos_before_b = self.pos
        b = self._read_object()
        if debug:
            print(f"DEBUG: b.b read from {pos_before_b}, now pos={self.pos}")

        # b.c = type 29
        pos_before_c = self.pos
        c = self._read_object()
        if debug:
            print(f"DEBUG: b.c read from {pos_before_c}, now pos={self.pos}")

        # b.d = ArrayList (type 14) - THIS IS THE LESSONS LIST
        pos_before_d = self.pos
        lessons = self._read_object()
        if debug:
            lessons_type = type(lessons).__name__
            lessons_len = len(lessons) if isinstance(lessons, list) else 'N/A'
            marker_val = self.data[pos_before_d-1] if pos_before_d > 0 else 'N/A'
            print(f"DEBUG: b.d read from {pos_before_d} (marker={marker_val}), type={lessons_type}, len={lessons_len}")
            if isinstance(lessons, list) and lessons:
                print(f"DEBUG: First lesson item: {type(lessons[0])}")

        # b.e = type 29
        e = self._read_object()
        # b.f = type 29
        f = self._read_object()
        # b.g = type 29
        g = self._read_object()
        # b.i = type 29
        i = self._read_object()
        # b.j = int
        j = self._pop()
        # b.k = int
        k = self._pop()
        # b.n = int
        n = self._pop()
        # b.o = int
        o = self._pop()
        # b.p = int
        p = self._pop()
        # b.q = type 102
        q = self._read_object()
        # b.r = boolean
        r = self._read_bool()
        # b.s = int
        s = self._pop()
        # b.t = int
        t = self._pop()
        # b.u = UDate (type 7)
        u = self._read_object()
        # b.v = type 29
        v = self._read_object()
        # b.w = ArrayList (type 14)
        w = self._read_object()
        # b.A = type 29
        A = self._read_object()
        # b.B = type 29
        B = self._read_object()

        return {
            '_class': 'PersSkemaData',
            'lessons': lessons if isinstance(lessons, list) else []
        }

    def _deserialize_aktiviteter(self) -> dict:
        """
        Deserialize AktiviteterISkema (aqg function).

        Has 5 fields (NOT 3!):
        b.a = a.b[--a.a]  // int
        b.b = a.b[--a.a]  // int
        b.c = pqd         // string (e.g. "HOLD")
        b.d = pqd         // string (e.g. "htxr24")
        b.e = a.b[--a.a]  // int
        """
        a = self._pop()  # int
        b = self._pop()  # int
        c = self._read_string()  # string (HOLD)
        d = self._read_string()  # string (hold code)
        e = self._pop()  # int
        return {'a': a, 'b': b, 'c': c, 'd': d, 'e': e}

    def _deserialize_enum(self) -> dict:
        """
        Deserialize enum types.

        In GWT, the enum factory function reads an ordinal value:
        function m4f(a) {
            var b = a.b[--a.a];  // read ordinal
            return enum_values[b];
        }
        The deserializer function is empty - no additional fields.
        """
        ordinal = self._pop()  # Read the ordinal value
        return {'_class': 'enum', 'ordinal': ordinal}

    def _deserialize_skema_note(self) -> dict:
        """Deserialize SkemaNote2."""
        a = self._pop()  # int (note_id?)
        b = self._read_string()  # text?
        c = self._pop()  # int
        d = self._read_string()  # html?
        e = self._read_string()  # plain?
        return {'id': a, 'text': b, 'html': d, 'plain': e}

    def _deserialize_aarstyp(self) -> dict:
        """
        Deserialize Aarstyp (p4f function).
        b.a = zUb(iqd(a), 405)  // AarsagsType
        b.b = zUb(iqd(a), 24)   // object
        b.c = a.b[--a.a]        // int
        b.d = zUb(iqd(a), 519)  // AmuKode
        b.e = pqd_pattern       // string
        b.f = zUb(iqd(a), 311)  // Status
        """
        a = self._read_object()  # AarsagsType
        b = self._read_object()  # object
        c = self._pop()          # int
        d = self._read_object()  # AmuKode
        e = self._read_string()  # string
        f = self._read_object()  # Status
        return {'_class': 'Aarstyp'}

    def _deserialize_frareg(self) -> dict:
        """
        Deserialize Frareg (ceg function).
        b.a = a.b[--a.a]        // int
        b.b = a.b[--a.a]        // int
        b.c = a.b[--a.a]        // int
        b.d = zUb(iqd(a), 312)  // Frareg$Status
        """
        a = self._pop()          # int
        b = self._pop()          # int
        c = self._pop()          # int
        d = self._read_object()  # Status
        return {'_class': 'Frareg'}

    def _deserialize_fravk(self) -> dict:
        """
        Deserialize Fravk (ugg function).
        b.a = pqd_pattern       // string
        b.b = pqd_pattern       // string
        b.c = pqd_pattern       // string
        b.d = zUb(iqd(a), 521)  // FravkStatus
        b.e = zUb(iqd(a), 24)   // object
        """
        a = self._read_string()  # string
        b = self._read_string()  # string
        c = self._read_string()  # string
        d = self._read_object()  # FravkStatus
        e = self._read_object()  # object
        return {'_class': 'Fravk'}

    def _deserialize_skemaelev(self) -> dict:
        """
        Deserialize Skemaelev (XGf function).
        b.a = BUb(iqd(a))       // boolean object
        b.b = BUb(iqd(a))       // boolean object
        b.c = zUb(iqd(a), 24)   // object
        b.d = pqd_pattern       // string
        b.e = zUb(iqd(a), 24)   // object
        b.f = pqd_pattern       // string
        b.g = zUb(iqd(a), 24)   // object
        b.i = pqd_pattern       // string
        b.pb = pqd_pattern      // string
        """
        a = self._read_object()  # boolean obj
        b = self._read_object()  # boolean obj
        c = self._read_object()  # object
        d = self._read_string()  # string
        e = self._read_object()  # object
        f = self._read_string()  # string
        g = self._read_object()  # object
        i = self._read_string()  # string
        pb = self._read_string() # string
        return {'_class': 'Skemaelev', 'name': f}

    def _deserialize_skema_uvfo(self) -> dict:
        """
        Deserialize SkemaUvfo (Wtg function).
        b.a = a.b[--a.a]        // int
        b.b = zUb(iqd(a), 7)    // UDate
        b.c = zUb(iqd(a), 7)    // UDate
        b.d = pqd_pattern       // string
        b.e = a.b[--a.a]        // int
        b.f = zUb(iqd(a), 7)    // UDate
        b.g = pqd_pattern       // string
        a.b[--a.a]              // skip
        b.i = a.b[--a.a]        // int
        b.j = a.b[--a.a]        // int
        b.k = a.b[--a.a]        // int
        b.n = zUb(iqd(a), 7)    // UDate
        b.o = zUb(iqd(a), 7)    // UDate
        """
        a = self._pop()          # int
        b = self._read_object()  # UDate
        c = self._read_object()  # UDate
        d = self._read_string()  # string
        e = self._pop()          # int
        f = self._read_object()  # UDate
        g = self._read_string()  # string
        self._pop()              # skip
        i = self._pop()          # int
        j = self._pop()          # int
        k = self._pop()          # int
        n = self._read_object()  # UDate
        o = self._read_object()  # UDate
        return {'_class': 'SkemaUvfo', 'name': d}

    def _deserialize_udate(self) -> Optional[datetime]:
        """
        Deserialize UDate (DKd function).

        Structure: [sec, min, hour, day, month, year, "UDate:"_idx, class_marker]
        The class marker is already consumed by _read_object.
        The "UDate:" marker is a SINGLE pop (not double like old buggy pqd).
        """
        # Read "UDate:" marker string (single pop - it's a string index)
        self._pop()  # discard "UDate:" marker (we don't need the string itself)

        year = self._pop()
        month = self._pop()
        day = self._pop()
        hour = self._pop()
        minute = self._pop()
        second = self._pop()

        try:
            return datetime(year + 1900, month + 1, day, hour, minute, second)
        except (ValueError, TypeError):
            return None

    def _deserialize_lokaler(self) -> dict:
        """
        Deserialize LokalerISkema (org function).

        b.a = a.b[--a.a]           // lokale_id
        b.b = pqd_pattern          // lokale navn
        b.c = a.b[--a.a]           // int
        """
        lokale_id = self._pop()
        lokale_navn = self._read_string()
        c = self._pop()

        return {
            'id': lokale_id,
            'navn': lokale_navn,
            'c': c
        }

    def _deserialize_medarbejder(self) -> dict:
        """
        Deserialize MedarbejderISkema (xrg function).

        b.a = a.b[--a.a]           // medarbejder_id
        b.b = pqd_pattern          // initialer/navn
        b.c = a.b[--a.a]           // int
        b.d = zUb(iqd(a), 24)      // nested object
        """
        medarbejder_id = self._pop()
        navn = self._read_string()
        c = self._pop()
        d = self._read_object()

        return {
            'id': medarbejder_id,
            'navn': navn,
            'c': c,
            'd': d
        }

    def _deserialize_skema_begivenhed(self) -> SkemaLesson:
        """
        Deserialize SkemaBegivenhed (Dqg function).

        38 fields read in order - see CLAUDE.md for full list.
        We only extract the fields we care about.
        """
        lesson = SkemaLesson()

        # b.a = aktivitetList (ArrayList)
        aktivitet_list = self._read_object()

        # b.c = bemerkning (string)
        bemerkning = self._read_string()

        # b.d = ? (string)
        d = self._read_string()

        # b.e = ? (boolean)
        e = self._read_bool()

        # b.f = ? (int)
        f = self._pop()

        # b.g = ? (type 24)
        g = self._read_object()

        # b.i = ? (ArrayList)
        i = self._read_object()

        # b.j = ? (int)
        j = self._pop()

        # b.k = ? (type 24)
        k = self._read_object()

        # b.n = ? (boolean)
        n = self._read_bool()

        # b.o = ? (ArrayList)
        o = self._read_object()

        # b.p = ? (type 406)
        p = self._read_object()

        # b.q = ? (int)
        q = self._pop()

        # b.r = ? (type 248)
        r = self._read_object()

        # b.s = ? (int)
        s = self._pop()

        # b.t = skoleFag (string) - SUBJECT (found by JS debugging!)
        skolefag = self._read_string()
        if skolefag:
            lesson.subject = skolefag

        # b.u = ? (boolean)
        u = self._read_bool()

        # b.w = ? (int)
        w = self._pop()

        # b.A = lokaleList (ArrayList) - ROOMS
        lokale_list = self._read_object()
        if isinstance(lokale_list, list):
            for lok in lokale_list:
                if isinstance(lok, dict) and lok.get('navn'):
                    lesson.rooms.append(lok['navn'])

        # b.B = ? (boolean)
        B = self._read_bool()

        # b.C = medarbejderList (ArrayList) - TEACHERS
        medarbejder_list = self._read_object()
        if isinstance(medarbejder_list, list):
            for med in medarbejder_list:
                if isinstance(med, dict) and med.get('navn'):
                    lesson.teachers.append(med['navn'])

        # b.D = ? (boolean)
        D = self._read_bool()

        # b.F = ? (string)
        F = self._read_string()

        # b.G = objekt_id (type 24)
        G = self._read_object()

        # b.H = ? (string)
        H = self._read_string()

        # b.I = ? (boolean)
        I = self._read_bool()

        # b.J = planlegger (string)
        J = self._read_string()

        # b.K = ? (boolean)
        K = self._read_bool()

        # b.L = ? (type 610)
        L = self._read_object()

        # b.M = ? (type 210)
        M = self._read_object()

        # b.N = ? (type 24)
        N = self._read_object()

        # b.O = ? (type 24)
        O = self._read_object()

        # b.P = ? (string) - Note: Subject is actually in b.t, not here
        P = self._read_string()

        # b.Q = slut (UDate) - END TIME
        slut = self._read_object()
        if isinstance(slut, datetime):
            lesson.end_time = slut

        # b.R = start (UDate) - START TIME
        start = self._read_object()
        if isinstance(start, datetime):
            lesson.start_time = start

        # b.S = ? (type 177)
        S = self._read_object()

        # b.T = ? (int)
        T = self._pop()

        # b.V = ? (boolean)
        V = self._read_bool()

        # Note from bemerkning
        if bemerkning:
            lesson.note = bemerkning

        return lesson

    def scan_for_lessons(self, debug: bool = False) -> List[SkemaLesson]:
        """
        Fallback scanner that directly extracts lesson patterns from data.

        This is used when the full deserializer doesn't reach the lesson data
        due to complex nesting.
        """
        lessons = []

        # Find SkemaBegivenhed class marker index in string table
        skema_marker = None
        for i, s in enumerate(self.strings):
            if s.startswith('dk.uddata.model.skema.SkemaBegivenhed/'):
                skema_marker = i + 1  # 1-based indexing
                break

        if skema_marker is None:
            if debug:
                print("DEBUG scan: SkemaBegivenhed not found in string table")
            return lessons

        if debug:
            print(f"DEBUG scan: SkemaBegivenhed marker = {skema_marker}")

        # Find all positions where SkemaBegivenhed marker appears
        positions = [i for i, v in enumerate(self.data) if v == skema_marker]
        if debug:
            print(f"DEBUG scan: Found {len(positions)} SkemaBegivenhed instances")

        # For each SkemaBegivenhed, try to extract lesson data
        for pos in positions:
            lesson = self._scan_lesson_at(pos, debug)
            if lesson and lesson.subject:  # Only add if we found a subject
                lessons.append(lesson)

        return lessons

    def _scan_lesson_at(self, pos: int, debug: bool = False) -> Optional[SkemaLesson]:
        """Scan for lesson data around a SkemaBegivenhed marker position."""
        lesson = SkemaLesson()

        # Find SkemaBegivenhed marker for boundary detection
        skema_marker = None
        for i, s in enumerate(self.strings):
            if s.startswith('dk.uddata.model.skema.SkemaBegivenhed/'):
                skema_marker = i + 1
                break

        # Skip patterns that look like student names, GWT markers, or other non-subject strings
        skip_patterns = {'HOLD', 'Skemaelev', 'UDate:'}

        # Skip absence reasons that aren't real subjects
        absence_reasons = {
            'Sygdom', 'FRI', 'Praktik', 'Session', 'Coronatest', 'Syg',
            'Omsorgsdag', 'Nedlukning', 'Graviditetsbet. sygdom',
            'SKO udeblevet', 'SKO - fri/søgedag', 'Kun for SKO',
            'VFU - AUB', 'Elevplads samtale', 'Speciallæge/-tandlæge',
            'Køre- og teoriprøve', 'Anden årsag', 'Familiebegivenhed',
            'Ikke godkendt fravær', 'Godkendt fravær', 'For sent',
            'Externt arrangement', 'K\u00f8re- og teoripr\u00f8ve',
            'Speciall\u00e6ge/-tandl\u00e6ge'
        }

        # Limit scan range - stop at the NEXT SkemaBegivenhed marker or after 120 positions
        scan_range = min(120, pos)

        for i in range(pos - 1, pos - scan_range - 1, -1):
            if i < 0:
                break

            val = self.data[i]

            # Stop if we hit another SkemaBegivenhed marker (boundary)
            if val == skema_marker:
                break

            # Skip non-string values
            if not isinstance(val, int) or val <= 0 or val > len(self.strings):
                continue

            s = self.strings[val - 1]

            # Skip class markers (contain "/" followed by digits)
            if '/' in s:
                parts = s.split('/')
                if len(parts) == 2 and parts[1].isdigit():
                    continue

            # Skip patterns in skip list
            if s in skip_patterns:
                continue

            # Skip absence reasons
            if s in absence_reasons:
                continue

            # Skip strings that look like student names (Two Capitalized Words)
            words = s.split()
            if len(words) == 2 and all(len(w) > 1 and w[0].isupper() and w[1:].islower() for w in words):
                continue

            # Subject: Look for longer capitalized strings
            if not lesson.subject and len(s) > 5:
                # Skip codes like htxe23, htxch23
                if s.startswith('htx') and any(c.isdigit() for c in s):
                    continue
                # Accept strings that start with uppercase and are mostly alphabetic
                if s[0].isupper():
                    alpha_ratio = sum(1 for c in s if c.isalpha()) / len(s)
                    if alpha_ratio > 0.6:
                        lesson.subject = s
                        if debug:
                            print(f"  Subject: {s}")

            # Room: typically short codes like M1304, A104, SO4, L002a, etc.
            if len(s) >= 2 and len(s) <= 6 and s[0].isupper() and any(c.isdigit() for c in s):
                if s not in lesson.rooms:
                    lesson.rooms.append(s)
                    if debug:
                        print(f"  Room: {s}")

            # Teacher: typically short initials like 'haje', 'abc', etc. (2-4 lowercase letters)
            if len(s) >= 2 and len(s) <= 4 and s.islower() and s.isalpha():
                if s not in lesson.teachers:
                    lesson.teachers.append(s)
                    if debug:
                        print(f"  Teacher: {s}")

        return lesson

    def _extract_lessons_recursive(self, obj: Any, lessons: List[SkemaLesson]):
        """Recursively extract SkemaLesson objects from any nested structure."""
        if isinstance(obj, SkemaLesson):
            lessons.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                self._extract_lessons_recursive(item, lessons)
        elif isinstance(obj, dict):
            for value in obj.values():
                self._extract_lessons_recursive(value, lessons)

    def parse_lessons(self, debug: bool = False) -> List[SkemaLesson]:
        """Parse all lessons from the response."""
        lessons = []

        # The response contains a top-level PersSkemaData object
        try:
            if debug:
                print(f"DEBUG: Starting parse, pos={self.pos}")
                print(f"DEBUG: First few values at stack top: {self.data[self.pos-5:self.pos]}")

            result = self._read_object()

            if debug:
                print(f"DEBUG: Result type: {type(result)}")

            # Recursively extract all SkemaLesson objects from the entire object graph
            self._extract_lessons_recursive(result, lessons)

            if debug:
                print(f"DEBUG: Found {len(lessons)} lessons total")
                print(f"DEBUG: Final position: {self.pos} (should be near 0)")
                print(f"DEBUG: Object cache size: {len(self.objects)}")

        except Exception as e:
            import traceback
            print(f"Parse error: {e}")
            traceback.print_exc()

        return lessons

    def parse_lessons_direct(self, debug: bool = False) -> List[SkemaLesson]:
        """
        Parse lessons by finding all SkemaBegivenhed markers and deserializing directly.

        This bypasses the complex PersSkemaData wrapper structure while still using
        the correct stack-based deserializers for each SkemaBegivenhed object.
        """
        lessons = []

        # Find SkemaBegivenhed class marker
        skema_marker = None
        for i, s in enumerate(self.strings):
            if s.startswith('dk.uddata.model.skema.SkemaBegivenhed/'):
                skema_marker = i + 1
                break

        if skema_marker is None:
            if debug:
                print("DEBUG: SkemaBegivenhed not found in string table")
            return lessons

        # Find all positions where SkemaBegivenhed marker appears
        positions = [i for i, v in enumerate(self.data) if v == skema_marker]
        if debug:
            print(f"DEBUG: Found {len(positions)} SkemaBegivenhed instances")

        # Deserialize each one
        for pos in positions:
            try:
                self.pos = pos
                self.objects = []  # Clear cache for each lesson
                lesson = self._deserialize_skema_begivenhed()
                if lesson.subject or lesson.rooms or lesson.teachers:
                    lessons.append(lesson)
                    if debug:
                        print(f"DEBUG: Lesson at {pos}: {lesson.subject} | {lesson.rooms} | {lesson.teachers}")
            except Exception as e:
                if debug:
                    print(f"DEBUG: Error at pos {pos}: {e}")
                continue

        return lessons


def parse_schedule_response(response: str) -> List[SkemaLesson]:
    """Parse a StudiePlus schedule GWT response and return lessons.

    Uses direct SkemaBegivenhed deserialization - finds all lesson markers
    and deserializes each using the correct stack-based reading.
    """
    parser = GWTDeserializer(response)
    return parser.parse_lessons_direct()


# Backwards compatibility
GWTResponseParser = GWTDeserializer
GWTScheduleParser = GWTDeserializer


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            response = f.read()

        lessons = parse_schedule_response(response)
        print(f"Found {len(lessons)} lessons")
        print()

        for lesson in lessons:
            print(lesson)
    else:
        print("Usage: python gwt_deserializer.py <response_file>")
