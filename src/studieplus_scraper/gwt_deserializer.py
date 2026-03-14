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
    class_name: str = ""  # Class name from aktivitet_list (e.g., "htxqr24")
    teachers: List[str] = field(default_factory=list)
    rooms: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    note: str = ""
    homework: str = ""  # Homework text (from SkemaNote2 containing "Lektier")
    has_homework: bool = False
    has_note: bool = False
    has_files: bool = False
    file_container_id: int = 0

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
            'dk.uddata.model.skemanoter.Note': self._deserialize_note,

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

            # Assignment types (Opgaver)
            'dk.uddata.model.opgave.Aflevering': self._deserialize_aflevering,
            'dk.uddata.model.opgave.OpgaveElev': self._deserialize_opgave_elev,
            'dk.uddata.model.opgave.AfleveringBedoemmelse': self._deserialize_aflevering_bedoemmelse,
            'dk.uddata.model.opgave.AfleveringStatus': self._deserialize_enum,
            'dk.uddata.model.opgave.BedoemmelsesForm': self._deserialize_enum,

            # User types needed for assignments
            'dk.uddata.model.bruger.Medarbejder': self._deserialize_bruger_medarbejder,
            'dk.uddata.model.bruger.Elev': self._deserialize_bruger_elev,
            'dk.uddata.gwt.comm.shared.user.RolleType': self._deserialize_enum,

            # Other assignment-related types
            'dk.uddata.model.undervisningsplan.UndervisningsforloebResume': self._deserialize_undervisningsforloeb_resume,
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
        # Ensure val is an integer for indexing
        if isinstance(val, float):
            val = int(val)
        if isinstance(val, int) and val > 0 and val <= len(self.strings):
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

        # Ensure b is an integer for comparisons and indexing
        if isinstance(b, float):
            b = int(b)

        if not isinstance(b, int):
            return None

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
        Deserialize PersSkemaData (Dmg function in new JS).

        This is the top-level response object.
        Field b.A contains the schedule as a HashMap: {UDate -> ArrayList<SkemaBegivenhed>}
        Field b.d is an ArrayList that may also contain lessons (legacy).
        """
        # b.a = type 29 (HashMap of Aarstyp)
        a = self._read_object()
        # b.b = UDate (type 7)
        b = self._read_object()
        # b.c = type 29 (HashMap)
        c = self._read_object()
        # b.d = ArrayList (type 14) - may contain lessons (legacy)
        d = self._read_object()
        # b.e = type 29 (HashMap)
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
        # b.w = ArrayList (type 14) - SkemaUvfo objects
        w = self._read_object()
        # b.A = type 29 (HashMap: {UDate -> ArrayList<SkemaBegivenhed>}) - SCHEDULE DATA
        A = self._read_object()
        # b.B = type 29
        B = self._read_object()

        # Extract lessons from b.A (HashMap by date) or fallback to b.d (legacy ArrayList)
        lessons = []
        if isinstance(A, dict):
            for date_key, date_lessons in A.items():
                if isinstance(date_lessons, list):
                    lessons.extend(date_lessons)
        if not lessons and isinstance(d, list):
            lessons = d

        return {
            '_class': 'PersSkemaData',
            'lessons': lessons
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
        """
        Deserialize SkemaNote2 (hAg function).

        Fields (16 total):
        b.a = int
        b.b = string
        b.c = int
        b.d = boolean
        b.e = string (homework HTML)
        b.f = string (homework plain text)
        b.g = string (note HTML)
        b.i = string (note plain text)
        b.j = object (type 24)
        b.k = string
        b.n = object (type 24)
        b.o = object (type 7 = UDate)
        b.p = object (type 24)
        b.q = int
        b.r = int
        b.s = string
        """
        a = self._pop()           # int
        b = self._read_string()   # string
        c = self._pop()           # int
        d = self._read_bool()     # boolean
        e = self._read_string()   # string - PLAIN TEXT (homework text!)
        f = self._read_string()   # string - HTML (homework html!)
        g = self._read_string()   # string
        i = self._read_string()   # string
        j = self._read_object()   # object (type 24)
        k = self._read_string()   # string
        n = self._read_object()   # object (type 24)
        o = self._read_object()   # object (type 7 = UDate)
        p = self._read_object()   # object (type 24)
        q = self._pop()           # int
        r = self._pop()           # int
        s = self._read_string()   # string

        # n is an Integer object — extract raw int value
        file_container_id = n if isinstance(n, int) else (n.get('value') if isinstance(n, dict) else None)

        return {
            '_class': 'SkemaNote2',
            'id': a,
            'class_name': b,
            'container_id': c,
            'has_files': d,
            'homework_html': e,
            'homework_text': f,
            'note_html': g,
            'note_text': i,
            'date': o,
            'file_container_id': file_container_id,
        }

    def _deserialize_note(self) -> dict:
        """
        Deserialize Note (Lzg function - line 26658).

        b.a = zUb(iqd(a), 24)   // object (Integer/SkemaObjekt)
        b.b = zUb(iqd(a), 169)  // object (Medarbejder/Bruger)
        b.c = zUb(iqd(a), 211)  // object (SkemaNote2)
        """
        a = self._read_object()  # Integer/SkemaObjekt
        b = self._read_object()  # Medarbejder/Bruger
        c = self._read_object()  # SkemaNote2
        return {
            '_class': 'Note',
            'skema_objekt': a,
            'bruger': b,
            'skema_note2': c,
        }

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

        # b.a = aktivitetList (ArrayList) - contains class info
        aktivitet_list = self._read_object()

        # Extract class_name from aktivitet_list
        if isinstance(aktivitet_list, list):
            for akt in aktivitet_list:
                if isinstance(akt, dict) and akt.get('d'):
                    lesson.class_name = akt['d']
                    break

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

        # b.N = skema_id (Integer type 24) - THIS IS THE LESSON ID!
        N = self._read_object()
        if isinstance(N, int):
            lesson.lesson_id = N

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

    # ==================== ASSIGNMENT DESERIALIZERS ====================

    def _deserialize_aflevering(self) -> dict:
        """
        Deserialize Aflevering (Ked function in fresh assignment JS).

        13 fields (updated from fresh JS source 2026-03-13):
        b.a = Gic(a), type 10   = UDate (submission datetime)
        b.b = Gic(a), type 239  = AfleveringBedoemmelse
        b.c = Gic(a), type 22   = ArrayList
        b.d = a.b[--a.a]        = int (container_id)
        b.e = Gic(a), type 149  = Elev
        b.f = Gic(a), type 212  = object
        b.g = Pic(a)            = boolean
        b.i = Pic(a)            = boolean
        b.j = Gic(a), type 43   = Long/Integer
        b.k = Gic(a), type 213  = OpgaveElev
        b.n = Gic(a), type 182  = AfleveringStatus
        b.o = Pic(a)            = boolean
        b.p = Gic(a), type 22   = ArrayList (NEW)
        """
        a = self._read_object()      # UDate = submission datetime
        b = self._read_object()      # AfleveringBedoemmelse
        c = self._read_object()      # ArrayList
        d = self._pop()              # int = container_id
        e = self._read_object()      # Elev
        f = self._read_object()      # object
        g = self._read_bool()        # boolean
        i = self._read_bool()        # boolean
        j = self._read_object()      # Long/Integer
        k = self._read_object()      # OpgaveElev
        n = self._read_object()      # AfleveringStatus
        o = self._read_bool()        # boolean
        p = self._read_object()      # ArrayList (NEW)

        return {
            '_class': 'Aflevering',
            'opgave_elev': k,
            'submission_date': a,
            'submitted': a is not None and isinstance(a, datetime),
            'status': n,
            'bedoemmelse': b,
            'container_id': d,
        }

    def _deserialize_opgave_elev(self) -> dict:
        """
        Deserialize OpgaveElev (ehd function - line 41046 in assignment_source_clean.js).

        This contains the actual assignment information we need:
        - subject (b.A)
        - title (b.v)
        - budget_hours (b.n)
        - spent_hours (b.o)
        - week (b.r)
        - deadline (b.D)
        - start_date (b.C)

        Fields read in order:
        hhd(b, Fic(a), 10)    -> b.f = object
        ihd(b, pop)           -> b.g = int
        jhd(b, Mic(a, pop))   -> b.i = string
        khd(b, Fic(a), 120)   -> b.j = object
        lhd(b, Mic(a, pop))   -> b.k = string
        mhd(b, Pic(a))        -> b.n = float (BUDGET HOURS)
        nhd(b, Pic(a))        -> b.o = float (SPENT HOURS)
        ohd(b, Fic(a), 10)    -> b.p = object
        phd(b, Fic(a), 10)    -> b.q = object
        qhd(b, pop)           -> b.r = int (WEEK)
        rhd(b, Fic(a), 112)   -> b.s = object
        shd(b, pop)           -> b.t = int
        thd(b, pop)           -> b.u = int
        uhd(b, Mic(a, pop))   -> b.v = string (TITLE)
        vhd(b, Oic(a))        -> b.w = boolean
        whd(b, Mic(a, pop))   -> b.A = string (SUBJECT)
        xhd(b, Fic(a), 130)   -> b.B = object
        yhd(b, Fic(a), 43)    -> b.C = object (START DATE)
        zhd(b, Fic(a), 43)    -> b.D = object (DEADLINE)
        Ahd(b, Oic(a))        -> b.F = boolean
        """
        f = self._read_object()      # type 10
        g = self._pop()              # int
        i = self._read_string()      # string
        j = self._read_object()      # type 120
        k = self._read_string()      # string
        n = float(self._pop())       # BUDGET HOURS (Pic = Number = float)
        o = float(self._pop())       # SPENT HOURS (Pic = Number = float)
        p = self._read_object()      # type 10
        q = self._read_object()      # type 10
        r = self._pop()              # WEEK number
        s = self._read_object()      # type 112
        t = self._pop()              # int
        u = self._pop()              # int
        v = self._read_string()      # TITLE
        w = self._read_bool()        # boolean
        A = self._read_string()      # SUBJECT
        B = self._read_object()      # type 130
        C = self._read_object()      # START DATE (UDate)
        D = self._read_object()      # DEADLINE (UDate)
        F = self._read_bool()        # boolean

        return {
            '_class': 'OpgaveElev',
            'opgave_id': g,  # b.g = OpgaveElev ID (used for getAflevering call)
            'subject': v,  # Data shows v contains subject (e.g., "Matematik")
            'title': A,    # Data shows A contains title (e.g., "Aflevering 4, 1.g")
            'budget_hours': n,
            'spent_hours': o,
            'week': r,
            'start_date': C,  # b.C = UDate (often null)
            'deadline': f,    # b.f = deadline shown in UI (lvc(b.f) in vQc line 46139)
            'class_name': i,  # i = class name like "htxqr24"
            'description': k,  # k = description HTML
        }

    def _deserialize_aflevering_bedoemmelse(self) -> dict:
        """
        Deserialize AfleveringBedoemmelse (Ced function - line 28976).

        Fed(b, pop)           -> b.a = int
        Ged(b, Fic(a), 43)    -> b.b = object (UDate?)
        Hed(b, Mic(a, pop))   -> b.c = string
        Ied(b, Mic(a, pop))   -> b.d = string
        Jed(b, pop)           -> b.e = int
        Ked(b, Fic(a), 10)    -> b.f = object
        Led(b, Fic(a), 112)   -> b.g = object
        """
        a = self._pop()              # int
        b = self._read_object()      # type 43 (UDate)
        c = self._read_string()      # string
        d = self._read_string()      # string (karakter/grade?)
        e = self._pop()              # int
        f = self._read_object()      # type 10
        g = self._read_object()      # type 112

        return {
            '_class': 'AfleveringBedoemmelse',
            'id': a,
            'date': b,
            'grade': d,
        }

    def _deserialize_bruger_base(self) -> dict:
        """
        Deserialize Bruger base class (U7c function - line 43596).

        This is the parent class for Medarbejder and Elev.
        """
        W7c = self._read_object()    # type 508
        X7c = self._read_object()    # type 43 (UDate)
        Y7c = self._read_string()    # string
        Z7c = self._read_object()    # object (wqb)
        dollar7c = self._read_string()  # string
        _7c = self._read_string()    # string
        a8c = self._read_object()    # type 10
        b8c = self._read_string()    # string
        c8c = self._read_string()    # string
        d8c = self._read_object()    # type 43 (UDate)
        e8c = self._read_string()    # string
        f8c = self._read_string()    # string
        g8c = self._read_object()    # object (wqb)
        h8c = self._read_object()    # object (wqb)
        i8c = self._read_object()    # object (wqb)
        j8c = self._read_object()    # object (wqb)
        k8c = self._read_object()    # type 10
        l8c = self._read_object()    # type 201
        m8c = self._read_object()    # type 10
        n8c = self._read_object()    # type 10
        o8c = self._read_string()    # string
        p8c = self._read_string()    # string
        q8c = self._read_string()    # string
        pb = self._read_string()     # string (rolle/pb)

        return {
            'initials': b8c,
            'name': Y7c,
            'rolle': pb,
        }

    def _deserialize_bruger_base(self) -> dict:
        """
        Deserialize Bruger base class (U7c function - line 43596).

        U7c reads 24 fields total.
        """
        W7c = self._read_object()    # 1. Fic (type 508)
        X7c = self._read_object()    # 2. Fic (type 43 - UDate)
        Y7c = self._read_string()    # 3. Mic (string)
        Z7c = self._read_object()    # 4. Fic (wqb)
        dollar_7c = self._read_string()  # 5. Mic (string)
        _7c = self._read_string()    # 6. Mic (string)
        a8c = self._read_object()    # 7. Fic (type 10 - Boolean)
        b8c = self._read_string()    # 8. Mic (string)
        c8c = self._read_string()    # 9. Mic (string - initials?)
        d8c = self._read_object()    # 10. Fic (type 43 - UDate)
        e8c = self._read_string()    # 11. Mic (string - name)
        f8c = self._read_string()    # 12. Mic (string)
        g8c = self._read_object()    # 13. Fic (wqb)
        h8c = self._read_object()    # 14. Fic (wqb)
        i8c = self._read_object()    # 15. Fic (wqb)
        j8c = self._read_object()    # 16. Fic (wqb)
        k8c = self._read_object()    # 17. Fic (type 10)
        l8c = self._read_object()    # 18. Fic (type 201)
        m8c = self._read_object()    # 19. Fic (type 10)
        n8c = self._read_object()    # 20. Fic (type 10)
        o8c = self._read_string()    # 21. Mic (string)
        p8c = self._read_string()    # 22. Mic (string)
        q8c = self._read_string()    # 23. Mic (string)
        pb = self._read_string()     # 24. Mic (string) - b.pb

        return {
            'name': e8c or '',
            'initials': c8c or '',
        }

    def _deserialize_bruger_medarbejder(self) -> dict:
        """
        Deserialize Medarbejder (c9c function - line 22738).

        f9c(b, Fic(a))        -> b.xx = object (wqb)
        g9c(b, pop)           -> b.yy = int
        h9c(b, pop)           -> b.zz = int
        i9c(b, Mic(a, pop))   -> b.aa = string
        U7c(a, b)             -> Bruger base class (15 fields)
        """
        f9c = self._read_object()    # object (wqb)
        g9c = self._pop()            # int
        h9c = self._pop()            # int
        i9c = self._read_string()    # string (initialer?)

        # Read Bruger base class fields
        base = self._deserialize_bruger_base()

        return {
            '_class': 'Medarbejder',
            'initialer': i9c or base.get('initials', ''),
            'name': base.get('name', ''),
        }

    def _deserialize_bruger_elev(self) -> dict:
        """
        Deserialize Elev (m8c function in fresh assignment JS).

        16 own fields (was 15, new string field b.J added) + 24 Bruger base:
        b.F = nqb(Gic(a))         -> object (cast boolean)
        b.G = lqb(Gic(a),10)      -> object (ArrayList)
        b.H = Pic(a)              -> boolean
        b.I = lqb(Gic(a),43)      -> object (Long/Integer)
        b.J = Nic(a,a.b[--a.a])   -> string (NEW!)
        b.K = lqb(Gic(a),43)      -> object (Long/Integer)
        b.L = nqb(Gic(a))         -> object (cast boolean)
        b.M = Pic(a)              -> boolean
        b.N = lqb(Gic(a),10)      -> object (ArrayList)
        b.O = Nic(a,a.b[--a.a])   -> string (elevnr)
        b.P = lqb(Gic(a),43)      -> object (Long/Integer)
        b.Q = Nic(a,a.b[--a.a])   -> string
        b.R = lqb(Gic(a),10)      -> object (ArrayList)
        b.S = Pic(a)              -> boolean
        b.T = Nic(a,a.b[--a.a])   -> string (klasse)
        b.U = lqb(Gic(a),43)      -> object (Long/Integer)
        A7c(a, b)                  -> Bruger base class (24 fields)
        """
        F = self._read_object()      # object (cast boolean)
        G = self._read_object()      # ArrayList
        H = self._read_bool()        # boolean
        I = self._read_object()      # Long/Integer
        J = self._read_string()      # string (NEW field)
        K = self._read_object()      # Long/Integer
        L = self._read_object()      # object (cast boolean)
        M = self._read_bool()        # boolean
        N = self._read_object()      # ArrayList
        O = self._read_string()      # string (elevnr)
        P = self._read_object()      # Long/Integer
        Q = self._read_string()      # string
        R = self._read_object()      # ArrayList
        S = self._read_bool()        # boolean
        T = self._read_string()      # string (klasse)
        U = self._read_object()      # Long/Integer

        base = self._deserialize_bruger_base()

        return {
            '_class': 'Elev',
            'elevnr': O,
            'klasse': T,
            'name': base.get('name', ''),
        }

    def _deserialize_undervisningsforloeb_resume(self) -> dict:
        """
        Deserialize UndervisningsforloebResume (Szd function - line 19679).

        Vzd(b, Mic(a, pop))   -> b.xx = string
        Wzd(b, Fic(a), 43)    -> b.yy = object (UDate)
        Xzd(b, Fic(a), 43)    -> b.zz = object (UDate)
        """
        title = self._read_string()  # string
        start = self._read_object()  # type 43 (UDate)
        end = self._read_object()    # type 43 (UDate)

        return {
            '_class': 'UndervisningsforloebResume',
            'title': title,
            'start': start,
            'end': end,
        }

    def parse_assignments(self, debug: bool = False, only_open: bool = False) -> List[dict]:
        """
        Parse assignment (Aflevering) objects from GWT response.

        Parses from the root ArrayList and extracts OpgaveElev data.

        Args:
            debug: Print debug info
            only_open: If True, only return non-submitted assignments

        Returns list of assignment dictionaries with:
        - subject
        - title
        - budget_hours / spent_hours
        - week
        - deadline
        - class_name
        - submitted (bool)
        - submission_date (str or empty)
        """
        # Reset position to start of data (read from end)
        self.pos = len(self.data)
        self.objects = []

        # Parse root object (should be ArrayList of Aflevering)
        try:
            root = self._read_object()
        except Exception as e:
            if debug:
                print(f"DEBUG: Error parsing root: {e}")
            return []

        if not isinstance(root, list):
            if debug:
                print(f"DEBUG: Root is not a list: {type(root)}")
            return []

        if debug:
            print(f"DEBUG: Parsed {len(root)} Aflevering objects from root")

        # Extract OpgaveElev from each Aflevering
        assignments = []
        for afl in root:
            if not isinstance(afl, dict):
                continue

            # Check submission status
            # submitted = True if submission_date exists
            submitted = afl.get('submitted', False)

            # Check status enum - AfleveringStatus (type 182):
            # 0 = AABEN (Open), 1 = LAAST (Locked), 2 = RETTET (Graded), 3 = AFVIST, 4 = AFVISTRETTET
            status = afl.get('status')
            status_ordinal = status.get('ordinal') if isinstance(status, dict) else None
            is_open_status = status_ordinal == 0 or status_ordinal is None  # AABEN or no status

            # Check if teacher has graded/evaluated (bedoemmelse has a date)
            bedoemmelse = afl.get('bedoemmelse')
            has_evaluation = False
            if isinstance(bedoemmelse, dict):
                eval_date = bedoemmelse.get('date')
                has_evaluation = eval_date is not None and eval_date != 0

            # Filter if only_open is requested
            # Assignment is "open" if: not submitted AND has open status AND not evaluated by teacher
            if only_open and (submitted or not is_open_status or has_evaluation):
                continue

            # Get OpgaveElev from Aflevering.j field
            opgave = afl.get('opgave_elev')
            if not isinstance(opgave, dict) or opgave.get('_class') != 'OpgaveElev':
                continue

            # Format deadline
            deadline_str = ''
            deadline = opgave.get('deadline')
            if isinstance(deadline, datetime):
                deadline_str = deadline.strftime('%d.%m.%Y %H:%M')
            elif isinstance(deadline, str):
                deadline_str = deadline

            # Format submission date
            submission_date_str = ''
            submission_date = afl.get('submission_date')
            if isinstance(submission_date, datetime):
                submission_date_str = submission_date.strftime('%d.%m.%Y %H:%M')

            # Skip if no meaningful data
            if not opgave.get('subject') and not opgave.get('title'):
                continue

            assignments.append({
                'container_id': afl.get('container_id'),  # ID for student's submitted files
                'opgave_id': opgave.get('opgave_id'),  # ID for teacher's attached files
                'subject': opgave.get('subject', ''),
                'title': opgave.get('title', ''),
                'description': opgave.get('description', ''),
                'deadline': deadline_str,
                'subject_budget_hours': str(opgave.get('budget_hours', '')),
                'hours_spent': str(opgave.get('spent_hours', '')),
                'class': opgave.get('class_name', ''),
                'week': str(opgave.get('week', '')),
                'submitted': submitted,
                'submission_date': submission_date_str,
            })

            if debug:
                print(f"DEBUG: Extracted: {opgave.get('subject')} - {opgave.get('title')} (submitted={submitted})")

        return assignments

    def parse_single_aflevering(self, debug: bool = False) -> dict:
        """
        Parse a single Aflevering from getAflevering response.

        Returns dict with all assignment details including container_id for files.
        """
        self.pos = len(self.data)
        self.objects = []

        try:
            afl = self._read_object()
        except Exception as e:
            if debug:
                print(f"DEBUG: Error parsing aflevering: {e}")
            return {}

        if not isinstance(afl, dict) or afl.get('_class') != 'Aflevering':
            if debug:
                print(f"DEBUG: Root is not Aflevering: {type(afl)}")
            return {}

        opgave = afl.get('opgave_elev')
        if not isinstance(opgave, dict):
            return {}

        # Format dates
        deadline_str = ''
        deadline = opgave.get('deadline')
        if isinstance(deadline, datetime):
            deadline_str = deadline.strftime('%d.%m.%Y %H:%M')

        submission_date_str = ''
        submission_date = afl.get('submission_date')
        if isinstance(submission_date, datetime):
            submission_date_str = submission_date.strftime('%d.%m.%Y %H:%M')

        # Get container_id from Aflevering (used for file lookup)
        # This is the 'c' field in the raw Aflevering
        container_id = afl.get('container_id', 0)

        return {
            'subject': opgave.get('subject', ''),
            'title': opgave.get('title', ''),
            'description': opgave.get('description', ''),
            'deadline': deadline_str,
            'subject_budget_hours': str(opgave.get('budget_hours', '')),
            'hours_spent': str(opgave.get('spent_hours', '')),
            'class': opgave.get('class_name', ''),
            'week': str(opgave.get('week', '')),
            'submitted': afl.get('submitted', False),
            'submission_date': submission_date_str,
            'container_id': container_id,
            'status': afl.get('status'),
            'bedoemmelse': afl.get('bedoemmelse'),
        }

    def parse_assignments_direct(self, debug: bool = False) -> List[dict]:
        """
        Parse assignments by directly finding and deserializing OpgaveElev objects.

        This approach finds all OpgaveElev markers in the data and deserializes
        each one from that position, extracting the fields we need.
        """
        assignments = []

        # Find OpgaveElev class marker
        opgave_marker = None
        for i, s in enumerate(self.strings):
            if s.startswith('dk.uddata.model.opgave.OpgaveElev/'):
                opgave_marker = i + 1
                break

        if opgave_marker is None:
            if debug:
                print("DEBUG: OpgaveElev not found in string table")
            return assignments

        if debug:
            print(f"DEBUG: OpgaveElev marker = {opgave_marker}")

        # Find all positions where OpgaveElev marker appears
        positions = [i for i, v in enumerate(self.data) if v == opgave_marker]
        if debug:
            print(f"DEBUG: Found {len(positions)} OpgaveElev instances")

        # Deserialize each OpgaveElev
        for pos in positions:
            try:
                # Set position to just after the marker (marker was at pos, so pos+1)
                self.pos = pos
                self.objects = []  # Clear cache for each assignment

                # Deserialize OpgaveElev fields
                opgave = self._deserialize_opgave_elev()

                # Format deadline
                deadline_str = ''
                deadline = opgave.get('deadline')
                if isinstance(deadline, datetime):
                    deadline_str = deadline.strftime('%d.%m.%Y %H:%M')

                # Only add if we got meaningful data
                if opgave.get('subject') or opgave.get('title'):
                    assignments.append({
                        'subject': opgave.get('subject', ''),
                        'title': opgave.get('title', ''),
                        'description': opgave.get('description', ''),
                        'deadline': deadline_str,
                        'subject_budget_hours': str(opgave.get('budget_hours', '')),
                        'hours_spent': str(opgave.get('spent_hours', '')),
                        'class': opgave.get('class_name', ''),
                        'week': str(opgave.get('week', '')),
                    })

                    if debug:
                        print(f"DEBUG: Parsed assignment at {pos}: {opgave.get('subject')} - {opgave.get('title')}")

            except Exception as e:
                if debug:
                    print(f"DEBUG: Error at pos {pos}: {e}")
                continue

        # Remove duplicates (same subject + title)
        seen = set()
        unique = []
        for a in assignments:
            key = (a['subject'], a['title'])
            if key not in seen:
                seen.add(key)
                unique.append(a)

        return unique

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

    def _parse_all_notes(self, debug: bool = False) -> List[dict]:
        """Parse all SkemaNote2 objects from the response."""
        notes = []

        # Find SkemaNote2 class marker
        note_marker = None
        for i, s in enumerate(self.strings):
            if 'SkemaNote2' in s:
                note_marker = i + 1
                break

        if note_marker is None:
            if debug:
                print("DEBUG: SkemaNote2 not found in string table")
            return notes

        # Find all positions where SkemaNote2 marker appears
        positions = [i for i, v in enumerate(self.data) if v == note_marker]
        if debug:
            print(f"DEBUG: Found {len(positions)} SkemaNote2 instances")

        # Deserialize each one
        for pos in positions:
            try:
                self.pos = pos
                self.objects = []
                note = self._deserialize_skema_note()
                has_content = (note.get('homework_text') or note.get('homework_html')
                              or note.get('note_text') or note.get('note_html'))
                if has_content:
                    notes.append(note)
                    if debug:
                        hw = str(note.get('homework_text', ''))[:50]
                        nt = str(note.get('note_text', ''))[:50]
                        print(f"DEBUG: Note at {pos}: date={note.get('date')}, hw={hw}, note={nt}")
            except Exception as e:
                if debug:
                    print(f"DEBUG: Error parsing note at pos {pos}: {e}")
                continue

        return notes

    def parse_lessons_direct(self, debug: bool = False) -> List[SkemaLesson]:
        """
        Parse lessons using proper top-down deserialization of PersSkemaData.

        Also parses SkemaNote2 objects and attaches them to lessons by date + class.
        The matching uses (date, class_name) to ensure homework is only attached
        to the correct lesson, not all lessons on the same day.
        """
        # First, parse all notes (before main deserialization resets pos)
        notes = self._parse_all_notes(debug=debug)

        # Group notes by (date, class_name) for robust matching
        notes_by_date_class = {}
        for note in notes:
            note_date = note.get('date')
            note_class = note.get('class_name', '')
            if note_date:
                if hasattr(note_date, 'strftime'):
                    date_key = note_date.strftime('%Y-%m-%d')
                else:
                    date_key = str(note_date)[:10]

                key = (date_key, note_class)
                if key not in notes_by_date_class:
                    notes_by_date_class[key] = []
                notes_by_date_class[key].append(note)

        # Reset state and do proper top-down deserialization
        self.pos = len(self.data)
        self.objects = []

        try:
            top = self._read_object()
        except Exception as e:
            if debug:
                print(f"DEBUG: Top-level deserialization failed: {e}")
            return []

        # Extract lessons from PersSkemaData result
        all_lessons = []
        if isinstance(top, dict):
            all_lessons = top.get('lessons', [])

        # Filter to only SkemaLesson objects
        lessons = [l for l in all_lessons if isinstance(l, SkemaLesson)]

        # Attach notes to lessons
        for lesson in lessons:
            if lesson.start_time:
                lesson_date = lesson.start_time.strftime('%Y-%m-%d')
                lesson_class = lesson.class_name or ''

                key = (lesson_date, lesson_class)
                if key in notes_by_date_class:
                    for note in notes_by_date_class[key]:
                        hw_text = note.get('homework_text', '') or ''
                        hw_html = note.get('homework_html', '') or ''
                        note_text = note.get('note_text', '') or ''
                        note_html = note.get('note_html', '') or ''

                        if hw_text or hw_html:
                            lesson.has_homework = True
                            lesson.homework = hw_text or hw_html[:200]
                        if note_text or note_html:
                            lesson.has_note = True
                            if not lesson.note or lesson.note == lesson.subject:
                                lesson.note = note_text or note_html[:200]
                        if note.get('has_files'):
                            lesson.has_files = True
                            lesson.file_container_id = note.get('container_id', 0)

        return lessons


def parse_schedule_response(response: str) -> List[SkemaLesson]:
    """Parse a StudiePlus schedule GWT response and return lessons.

    Uses direct SkemaBegivenhed deserialization - finds all lesson markers
    and deserializes each using the correct stack-based reading.
    """
    parser = GWTDeserializer(response)
    return parser.parse_lessons_direct()


def parse_assignments_response(response: str, debug: bool = False) -> List[dict]:
    """Parse a StudiePlus assignments (Opgaver) GWT response.

    Uses stack-based deserialization following the exact GWT deserializer logic
    from assignment_source_clean.js.

    Returns list of assignment dictionaries with:
    - subject: Subject name (e.g., "Matematik")
    - title: Assignment title
    - description: Assignment description (HTML)
    - deadline: Deadline as string (DD.MM.YYYY HH:MM)
    - subject_budget_hours: Budgeted hours for subject
    - hours_spent: Hours spent on assignment
    - class: Class name (e.g., "htxqr24")
    - week: Week number
    """
    parser = GWTDeserializer(response)
    return parser.parse_assignments(debug=debug)


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
