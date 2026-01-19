# GWT Reverse Engineering Guide

Denne guide dokumenterer processen for at reverse engineere GWT-RPC deserializering fra StudiePlus.

## Oversigt

GWT (Google Web Toolkit) kompilerer Java-kode til JavaScript. Serialiseringsformatet er baseret på Java-klassedefinitioner, som ikke er direkte tilgængelige. For at deserialisere data korrekt skal vi:

1. Forstå GWT response-formatet
2. Finde klasse-markører i string table
3. Ekstraktere felt-rækkefølge fra JavaScript-koden
4. Implementere en parser baseret på denne viden

## GWT Response Format

```
//OK[data..., count, flags, ["string_table"], version]
```

- `//OK` eller `//EX` prefix (success/exception)
- `data` - flat array med alle værdier og klasse-markører
- `count` - antal elementer
- `flags` - serialiseringsflag
- `string_table` - array af alle strenge (klasse-navne, felt-værdier)
- `version` - GWT version

### String Table

String table indeholder:
- Klasse-deskriptorer: `dk.uddata.model.skema.SkemaBegivenhed/786457974`
- Felt-værdier: `"Fysik"`, `"M1302"`, `"haje"`
- Enum-værdier og andre strenge

**Vigtigt:** GWT bruger 1-baseret indeksering (0 = null)

## Trin 1: Find Klasse-Markører

Parse response og find klasse-navne i string table:

```python
# String table er typisk næstsidste element i JSON-arrayet
for i, s in enumerate(strings):
    if 'SkemaBegivenhed/' in s:
        SKEMA_MARKER = i + 1  # 1-baseret!
```

## Trin 2: Find Deserializer-Funktionen i JavaScript

GWT registrerer deserializers sådan:

```javascript
// I source_clean.js
a[dUi] = [Eqg, Dqg, Fqg];
//        ^     ^     ^
//        |     |     +-- serializer
//        |     +-------- deserializer (DEN VI SKAL BRUGE)
//        +-------------- instantiate/factory
```

Find registreringen:
```bash
rg "SkemaBegivenhed" source_clean.js
# Output: dUi = "dk.uddata.model.skema.SkemaBegivenhed/786457974"

rg "dUi.*=" source_clean.js
# Output: a[dUi] = [Eqg, Dqg, Fqg];
```

## Trin 3: Analysér Deserializer-Funktionen

Find deserializer-funktionen (Dqg i dette tilfælde):

```bash
rg "^function Dqg" source_clean.js -A 50
```

Output viser felt-læsning:
```javascript
function Dqg(a, b) {
  Gqg(b, zUb(iqd(a), 14));       // Felt 1: aktivitetList
  Hqg(b, pqd(a, a.b[--a.a]));    // Felt 2: bemerkning (string)
  // ...
  frg(b, pqd(a, a.b[--a.a]));    // Felt 33: skoleFag (subject)
  grg(b, zUb(iqd(a), 7));        // Felt 34: slut (UDate)
  hrg(b, zUb(iqd(a), 7));        // Felt 35: start (UDate)
  // ...
}
```

### Forstå Læse-Funktionerne

- `a.b[--a.a]` - læs rå værdi fra stack
- `pqd(a, x)` - læs string ved index x
- `zUb(iqd(a), type)` - læs objekt af given type
- `rqd(a)` - læs boolean

## Trin 4: Find Setter-Funktionerne

Find hvad setter-funktionerne gør:

```bash
rg "^function [G-Z]qg\(" source_clean.js -A 2
```

Output:
```javascript
function Hqg(a, b) { a.c = b; }  // sætter felt 'c' (bemerkning)
function frg(a, b) { a.P = b; }  // sætter felt 'P' (skoleFag)
function grg(a, b) { a.Q = b; }  // sætter felt 'Q' (slut)
function hrg(a, b) { a.R = b; }  // sætter felt 'R' (start)
```

## Trin 5: Find Felt-Navne fra toString()

Find toString()-metoden for at se felt-navne:

```bash
rg "SkemaBegivenhed{" source_clean.js -B 5 -A 30
```

Output:
```javascript
"SkemaBegivenhed{planlegger='" + this.J +
", objekt_id=" + this.G +
", start=" + this.R +           // R = starttid
", slut=" + this.Q +            // Q = sluttid
", skoleFag='" + this.P +       // P = fag
", medarbejderList=" + this.C + // C = lærere
", lokaleList=" + this.A +      // A = lokaler
```

## Trin 6: Find Type-ID'er

Find type-registreringer:

```bash
rg "ASh.*SkemaBegivenhed" source_clean.js
# Output: var VJc = ASh(FJi, "SkemaBegivenhed", 35);
# Type 35 = SkemaBegivenhed

rg "ASh.*UDate" source_clean.js
# Output: var bic = ASh(hyi, "UDate", 7);
# Type 7 = UDate
```

## Trin 7: Analysér Nested Types

For nested types (UDate, MedarbejderISkema, etc.), gentag processen:

### UDate Deserializer

```javascript
function DKd(a, b) {
  var c = pqd(a, a.b[--a.a]);           // "UDate:" marker
  b.q.setTime(0);
  NRb(b, a.b[--a.a]);  // year (+1900)
  KRb(b, a.b[--a.a]);  // month (0-baseret)
  HRb(b, a.b[--a.a]);  // day
  IRb(b, a.b[--a.a]);  // hours
  JRb(b, a.b[--a.a]);  // minutes
  LRb(b, a.b[--a.a]);  // seconds
}
```

### MedarbejderISkema

```javascript
// Registrering: a[mUi] = [yrg, wrg, xrg]
// wrg er deserializeren
function wrg(a, b) {
  b.a = a.b[--a.a];      // medarbejder_id
  b.b = pqd(a, ...);     // navn (initialer)
  b.c = a.b[--a.a];      // anden værdi
}
```

## Komplet Felt-Mapping for SkemaBegivenhed

Baseret på analysen:

| Felt # | Setter | Property | Type | Beskrivelse |
|--------|--------|----------|------|-------------|
| 1 | Gqg | a | ArrayList | aktivitetList |
| 2 | Hqg | c | String | bemerkning |
| 19 | Vqg | A | ArrayList | lokaleList (rooms) |
| 21 | Xqg | C | ArrayList | medarbejderList (teachers) |
| 33 | frg | P | String | skoleFag (subject) |
| 34 | grg | Q | UDate | slut (end time) |
| 35 | hrg | R | UDate | start (start time) |

## Tips til Nye Objekttyper

1. **Find klasse-navnet** i string table
2. **Find registreringen** `a[klasseName] = [factory, deserializer, serializer]`
3. **Analysér deserializer-funktionen** for felt-rækkefølge
4. **Find setter-funktioner** for at mappe til property-navne
5. **Find toString()** for human-readable felt-navne
6. **Gentag for nested types**

## Værktøjer

```bash
# Søg efter klasse-navn
rg "KlasseNavn" source_clean.js

# Find registrering
rg "variabelNavn.*=" source_clean.js | grep "\[.*,.*,.*\]"

# Find deserializer
rg "^function FunktionsNavn" source_clean.js -A 50

# Find setters
rg "^function [A-Z][a-z]+\(" source_clean.js -A 2 | grep "a\."
```

## Begrænsninger

- **Obfuskeret kode** - variabel-navne er manglede
- **Ingen felt-navne i wire-format** - må udledes fra JS
- **Versionering** - GWT kan ændre serialiseringsformat
- **Nested kompleksitet** - dybt nestede objekter kræver rekursiv analyse
