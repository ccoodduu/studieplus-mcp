# StudiePlus MCP Server - Projektviden

## Projekt

MCP server der giver Claude Desktop adgang til en dansk elevs skoledata fra Studie+.
Bruger GWT-RPC API direkte (ingen browser) via `requests`-biblioteket.

### Krav til GWT-parsing
- **INGEN magic numbers** eller hacky løsninger
- **Parse data på SAMME måde som JavaScript-koden gør** (stack-baseret)
- Hvis der er udfordringer: **meld tilbage i stedet for at ændre plan**
- **ALTID** følg JS-kodens læserækkefølge

---

## GWT-RPC Format

### Response struktur
```
//OK[data..., ["string_table"], flags, version]
```

- `//OK` eller `//EX` prefix (success/exception)
- `data` - flat array, læses bagfra (stack)
- `string_table` - 1-baseret indeksering (0 = null)

### Læsefunktioner
- `a.b[--a.a]` — pop int fra stack
- `pqd(a, val)` — string lookup: `val > 0 ? strings[val-1] : null` (SINGLE pop, babel-inlined version ser ud som 2 pops men er 1)
- `!!a.b[--a.a]` — boolean
- `iqd(a)` — objekt: pop, negativ=back-reference, positiv=klasse fra string table, 0=null

---

## Vigtige Deserializers

### Note (Lzg — source_babel_inlined.js:26658)
Top-level response fra `hentNoteForSkema(lessonId)`.
```javascript
function Lzg(a, b) {
  b.a = zUb(iqd(a), 24);    // Integer (SkemaObjekt ID)
  b.b = zUb(iqd(a), 169);   // Medarbejder (lærer)
  b.c = zUb(iqd(a), 211);   // SkemaNote2
}
```

### SkemaNote2 (hAg — source_babel_inlined.js:53626)
16 felter. **VIGTIGT:** `b.c` er IKKE fil-container. `b.n` er fil-container.
```
b.a  = int              — note ID
b.b  = string           — klasse-navn (f.eks. "htxqr24")
b.c  = int              — schedule container_id (IKKE til filer!)
b.d  = boolean          — has_files
b.e  = string           — lektier tekst
b.f  = string           — lektier HTML
b.g  = string           — note tekst
b.i  = string           — note HTML
b.j  = object (Integer) — schedule container (samme som b.c)
b.k  = string
b.n  = object (Integer) — FILE container_id (BRUG DENNE til filer!)
b.o  = object (UDate)
b.p  = object (Integer)
b.q  = int
b.r  = int
b.s  = string
```

### SkemaBegivenhed (Dqg — source_babel_inlined.js:62180)
Vigtige felter:
- `b.P` = skoleFag (subject/fag)
- `b.Q` = slut (UDate)
- `b.R` = start (UDate)
- `b.A` = lokaleList (ArrayList af LokalerISkema)
- `b.C` = medarbejderList (ArrayList af MedarbejderISkema)

### ArrayList, UDate, LokalerISkema, MedarbejderISkema
Se `gwt_deserializer.py` for implementering — følger JS præcist.

---

## Fil-download Flow (3 trin)

Bekræftet via Playwright network capture. Websiden bruger dette flow:

1. **`skemanoteservice.hentNoteForSkema(lessonId)`** → Note objekt med SkemaNote2
2. **`ressourceservice.findRessourcerPerContainer(file_container_id, SKEMANOTE=12)`** → filliste
3. **`ressourceservice.hentRessourceUrl(fileId, "")`** → signeret S3 URL

`file_container_id` kommer fra SkemaNote2 felt `b.n` (IKKE `b.c`).
`hentRessourceUrl` tager fil-ID og en TOM string som 2. parameter.

### Signerede URLs
Format: `https://cellar-c2.services.clever-cloud.com/prod-{instnr}/{uuid}?X-Amz-...`
Gyldige i ~5 minutter.

---

## Vigtige Filer

- `gwt_analysis/source_babel_inlined.js` — JS med inlinede funktioner (brug til analyse)
- `gwt_analysis/source_clean.js` — Original JS kode
- `src/studieplus_scraper/gwt_deserializer.py` — Stack-baseret GWT parser
- `src/studieplus_scraper/requests_scraper.py` — HTTP-baseret scraper (GWT-RPC kald)
- `src/studieplus_scraper/api.py` — API lag mellem scraper og MCP
- `src/mcp_server/server.py` — MCP server tools
- `GWT_REVERSE_ENGINEERING.md` — Guide til at reverse engineere nye GWT typer
