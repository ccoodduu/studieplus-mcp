# GWT Data Structure Documentation

## Overview
StudiePlus uses Google Web Toolkit (GWT) RPC for communication. The response format is:
```
//OK[data...,N,M,["string_table"],flags]
```

## Key Classes (from source.js analysis)

### SkemaBegivenhed (Class ID: 35)
Main lesson/event class with these properties:
- `.R` = start time (UDate object)
- `.Q` = slut/end time (UDate object)
- `.N` = skemabeg_id (lesson ID)
- `.G` = objekt_id
- `.P` = skoleFag (school subject)
- `.c` = bemerkning (remark/note)
- `.w` = lektionsNummer
- `.C` = medarbejderList (teachers)
- `.A` = lokaleList (rooms)
- `.o` = fagList (subjects)
- `.p` = fravaStatus (absence status)

### UDate (Class ID: 7)
Date/time object. Serialized as:
```
[string_index "UDate:"], [encoded_value], [type_marker]
```

Deserialization reads (in stack order):
1. NRb → setFullYear(value + 1900)
2. KRb → setMonth(value)
3. HRb → setDate(value)
4. IRb → setHours(value)
5. JRb → setMinutes(value)
6. LRb → setSeconds(value)

### SkemaNote2 (Class ID: 211)
Note class with properties: a, c, d, e, f, g, i, q, r
String marker: `dk.uddata.model.skemanoter.SkemaNote2/106335929`

## Data Format Variations by Week

### Week 0 (Current Week) - Uses -714 markers
Detailed time blocks with separate fields:
```
-714, 0, MIN1, HOUR1, DAY, 0, YEAR, 30, 29, 0, MIN2, HOUR2, DAY, 0, YEAR, 30, 29, SUBJECT_IDX, LESSON_ID, ...
```

Offsets from -714 marker:
- +2: start minute
- +3: start hour
- +4: day of month
- +6: year (124=2024, 125=2025, 126=2026, 127=2027)
- +10: end minute
- +11: end hour
- +17: subject string index
- +18: lesson_id
- +35 to +55: teacher (position varies, search this range)
- +39 to +55: room (position varies, search this range)

### Week 1 - Uses -296 markers
Same structure as Week 0, but with different marker:
```
-296, 0, MIN1, HOUR1, DAY, 0, YEAR, 30, 29, 0, MIN2, HOUR2, DAY, ...
```

### Week 2+ - Uses encoded timestamps
Different format with single encoded timestamp value:
```
LESSON_ID, some_id, -12xx_marker, ..., UDate:, ENCODED_TIMESTAMP, ...
```

**Timestamp Encoding:**
- Values like 2689870, 2690631 are minutes since epoch ~2020-12-22
- To decode: `epoch + timedelta(minutes=value)`
- Example: 2689870 = 2026-02-01 23:10, 2690631 = 2026-02-02 11:51

**Decoding formula:**
```python
from datetime import datetime, timedelta
EPOCH = datetime(2020, 12, 22)
timestamp = EPOCH + timedelta(minutes=encoded_value)
```

### Summary of Markers by Week
| Week | Marker | Time Format |
|------|--------|-------------|
| 0 | -714 | Separate min/hour/day fields |
| 1 | -296 | Separate min/hour/day fields |
| 2 | -861 | Separate min/hour/day fields |
| 3+ | Various (-9xx to -12xx) | Separate min/hour/day fields |

**IMPORTANT FINDING:** All weeks use the SAME time block structure!
The only difference is the marker value. The pattern is always:
```
MARKER, 0, MIN1, HOUR1, DAY, [0|1], YEAR, 30, 29, 0, MIN2, HOUR2, DAY, [0|1], YEAR, 30, 29, TYPE, LESSON_ID
```

To detect time blocks, check for:
- Negative integer in range -1500 to -100
- Followed by 0
- Then minute (0-59), hour (6-20), day (1-31), 0 or 1, year (124-127)

## Summary Block Structure (all weeks)
28 positions starting with lesson_id:
- +0: lesson_id
- +6: day of month
- +8: year marker
- +16/+17: NOTE content (if different values = has note)
- +18/+19: HW content (if not placeholder = has homework)

## Placeholder Detection
Placeholders are strings that are:
- Empty
- Short (< 30 chars) without HTML tags or parentheses
- Subject names

Content strings typically have:
- HTML tags (`<font`, `<div`)
- Longer than 50 characters

## Known String Indices (varies by response)
These are common patterns, not fixed indices:
- `java.util.ArrayList/4159755760` - array marker
- `UDate:` - date marker
- `dk.uddata.model.skema.Aarstyp/211660552` - year type
- `dk.uddata.model.skemanoter.SkemaNote2/106335929` - note marker

## TODO
- [ ] Implement unified parser for all week formats
- [ ] Decode the large timestamp values (e.g., 2689867)
- [ ] Handle edge cases for year transitions
