# StudiePlus MCP Server - Projektviden

## Aktuel Opgave: GWT Deserializer

### Mål
Parse GWT-RPC schedule data fra StudiePlus på en robust måde.

### Krav (VIGTIGE - FØLG DISSE)
- **INGEN magic numbers**
- **INGEN hacky løsninger** (pattern matching på kendte fag-navne, range scanning)
- **Parse data på SAMME måde som JavaScript-koden gør** (stack-baseret)
- Hvis der er udfordringer: **meld tilbage i stedet for at ændre plan**

### Tilgang
1. Brug `source_babel_inlined.js` til at forstå præcis hvordan felter læses
2. Implementer en Python deserializer der gør det samme som JS-koden
3. Stack-baseret læsning: `a.b[--a.a]` = pop fra data array

---

## GWT-RPC Format

### Response struktur
```
//OK[data..., count, flags, ["string_table"], version]
```

- `//OK` eller `//EX` prefix (success/exception)
- `data` - flat array med alle værdier og klasse-markører
- `string_table` - array af alle strenge (1-baseret indeksering, 0 = null)

### Læsefunktioner i JS

**Primitiver:**
- `a.b[--a.a]` - pop rå værdi fra stack (int)
- `a.b[--a.a] > 0 ? a.d[a.b[--a.a] - 1] : null` - læs string (pqd pattern)
- `!!a.b[--a.a]` - læs boolean

**Objekter via iqd (source_babel_inlined.js:42774):**
```javascript
function iqd(a) {
  b = a.b[--a.a];              // pop værdi
  if (b < 0) {
    return Ao(a.e, -(b + 1));  // back-reference til tidligere objekt
  }
  c = b > 0 ? a.d[b - 1] : null;  // hent klasse-string fra string table
  if (c == null) return null;
  // deserialiser via Qrd og gem i object cache
  return Qrd(a.c, a, c);
}
```

**zUb er bare type-cast:** `zUb(iqd(a), type)` = læs objekt og cast til type

---

## SkemaBegivenhed (Lektion)

### Deserializer: Dqg funktionen (source_babel_inlined.js:62180)

```javascript
function Dqg(a, b) {
  b.a = zUb(iqd(a), 14);      // aktivitetList (ArrayList)
  b.c = pqd_pattern;           // bemerkning (string)
  b.d = pqd_pattern;           // ? (string)
  b.e = !!a.b[--a.a];          // ? (boolean)
  b.f = a.b[--a.a];            // ? (int)
  b.g = zUb(iqd(a), 24);       // ? (type 24)
  b.i = zUb(iqd(a), 14);       // ? (ArrayList)
  b.j = a.b[--a.a];            // ? (int)
  b.k = zUb(iqd(a), 24);       // ? (type 24)
  b.n = !!a.b[--a.a];          // ? (boolean)
  b.o = zUb(iqd(a), 14);       // ? (ArrayList)
  b.p = zUb(iqd(a), 406);      // ? (type 406)
  b.q = a.b[--a.a];            // ? (int)
  b.r = zUb(iqd(a), 248);      // ? (type 248)
  b.s = a.b[--a.a];            // ? (int)
  b.t = pqd_pattern;           // ? (string)
  b.u = !!a.b[--a.a];          // ? (boolean)
  b.w = a.b[--a.a];            // ? (int)
  b.A = zUb(iqd(a), 14);       // lokaleList (ArrayList) - LOKALER/ROOMS
  b.B = !!a.b[--a.a];          // ? (boolean)
  b.C = zUb(iqd(a), 14);       // medarbejderList (ArrayList) - LÆRERE/TEACHERS
  b.D = !!a.b[--a.a];          // ? (boolean)
  b.F = pqd_pattern;           // ? (string)
  b.G = zUb(iqd(a), 24);       // objekt_id (type 24)
  b.H = pqd_pattern;           // ? (string)
  b.I = !!a.b[--a.a];          // ? (boolean)
  b.J = pqd_pattern;           // planlegger (string)
  b.K = !!a.b[--a.a];          // ? (boolean)
  b.L = zUb(iqd(a), 610);      // ? (type 610)
  b.M = zUb(iqd(a), 210);      // ? (type 210)
  b.N = zUb(iqd(a), 24);       // ? (type 24)
  b.O = zUb(iqd(a), 24);       // ? (type 24)
  b.P = pqd_pattern;           // skoleFag (string) - FAG/SUBJECT
  b.Q = zUb(iqd(a), 7);        // slut (UDate) - SLUTTID
  b.R = zUb(iqd(a), 7);        // start (UDate) - STARTTID
  b.S = zUb(iqd(a), 177);      // ? (type 177)
  b.T = a.b[--a.a];            // ? (int)
  b.V = !!a.b[--a.a];          // ? (boolean)
}
```

### Vigtige felter
- `b.P` = skoleFag (subject/fag)
- `b.Q` = slut (end time, UDate)
- `b.R` = start (start time, UDate)
- `b.A` = lokaleList (rooms/lokaler)
- `b.C` = medarbejderList (teachers/lærere)

---

## Nested Types

### ArrayList (source_babel_inlined.js:24223)
```javascript
function Fod(a, b) {
  e = a.b[--a.a];        // pop antal elementer
  for (c = 0; c < e; ++c) {
    d = iqd(a);          // læs hvert element som objekt
    b.Ke(d);             // tilføj til listen
  }
}
```
**Format:** `[element1, element2, ..., elementN, count, class_marker]`

### LokalerISkema (source_babel_inlined.js:24926)
```javascript
function org(a, b) {
  b.a = a.b[--a.a];                                    // int (lokale_id)
  b.b = a.b[--a.a] > 0 ? a.d[a.b[--a.a] - 1] : null;  // string (lokale navn)
  b.c = a.b[--a.a];                                    // int
}
```
**Format:** `[c, navn_idx, a, class_marker]`
**Vigtigt felt:** `b.b` = lokale navn (string)

### MedarbejderISkema (source_babel_inlined.js:31005)
```javascript
function xrg(a, b) {
  b.a = a.b[--a.a];                                    // int (medarbejder_id)
  b.b = a.b[--a.a] > 0 ? a.d[a.b[--a.a] - 1] : null;  // string (initialer/navn)
  b.c = a.b[--a.a];                                    // int
  b.d = zUb(iqd(a), 24);                              // nested object (type 24)
}
```
**Format:** `[type24_obj, c, navn_idx, a, class_marker]`
**Vigtigt felt:** `b.b` = lærer initialer/navn (string)

### UDate (source_babel_inlined.js:46953)
```javascript
function DKd(a, b) {
  c = a.b[--a.a] > 0 ? a.d[a.b[--a.a] - 1] : null;  // "UDate:" marker string
  b.q.setTime(0);
  NRb(b, a.b[--a.a]);  // year (+1900)
  KRb(b, a.b[--a.a]);  // month (0-baseret)
  HRb(b, a.b[--a.a]);  // day
  IRb(b, a.b[--a.a]);  // hours
  JRb(b, a.b[--a.a]);  // minutes
  LRb(b, a.b[--a.a]);  // seconds
}
```
**Format:** `[sec, min, hour, day, month, year, "UDate:"_idx, class_marker]`

---

## Klasse-strenge i String Table

- `java.util.ArrayList/4159755760` → ArrayList
- `dk.uddata.gwt.comm.shared.UDate/...` → UDate
- `dk.uddata.model.skema.SkemaBegivenhed/...` → SkemaBegivenhed
- `dk.uddata.model.skema.SkemaBegivenhed$LokalerISkema/...` → LokalerISkema
- `dk.uddata.model.skema.SkemaBegivenhed$MedarbejderISkema/...` → MedarbejderISkema

---

## Implementerings-algoritme

1. Parse response → få data array og string table
2. Sæt stack pointer til starten af data
3. For at læse et objekt:
   - Pop værdi fra stack
   - Hvis negativ: return objekt fra cache ved `-(værdi + 1)`
   - Hvis positiv: hent klasse-string fra `strings[værdi - 1]`
   - Match klasse-string og kald den relevante deserializer
   - Gem objekt i cache og return det
4. Deserializers læser felter ved at poppe værdier i rækkefølge

---

## Vigtige Filer

- `source_babel_inlined.js` - JS med inlinede funktioner (brug denne til analyse)
- `source_clean.js` - Original JS kode
- `gwt_deserializer.py` - Nuværende parser (skal omskrives)
- `debug_gwt_response_20260119.txt` - Test data
- `GWT_REVERSE_ENGINEERING.md` - Dokumentation af reverse engineering proces

---

## Problemer at undgå

- **IKKE** scan efter kendte fag-navne (pattern matching)
- **IKKE** brug range scanning for at finde data
- **IKKE** skift plan uden at melde tilbage først
- **ALTID** følg JS-kodens læserækkefølge
