"""
Unit tests for GWT string-table decoding.

These do not touch the network and run without credentials. They pin down how
escapes and literal non-ASCII characters in a GWT response must survive
parsing — StudiePlus sends both forms, and getting it wrong silently mangles
Danish letters in teacher names, notes and file names.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from studieplus_scraper.requests_scraper import GWTParser


def decode(raw: str) -> str:
    return GWTParser._decode_escapes(raw)


def test_escaped_danish_letters():
    """The schedule note service escapes non-ASCII as \\uXXXX."""
    assert decode("\\u00f8velse i tegns\\u00e6tning") == "øvelse i tegnsætning"


def test_literal_danish_letters():
    """The resource service sends non-ASCII literally — it must survive."""
    assert decode("øvelse i tegnsætning") == "øvelse i tegnsætning"


def test_mixed_escaped_and_literal():
    assert decode("\\u00e5r år") == "år år"


def test_escaped_quote_and_newline():
    assert decode('sig \\"hej\\"') == 'sig "hej"'
    assert decode("linje1\\nlinje2") == "linje1\nlinje2"


def test_characters_above_latin1_survive():
    """Characters outside Latin-1 must not be corrupted by the codec hop."""
    assert decode("pris 100€") == "pris 100€"
    assert decode("godt \U0001f600") == "godt \U0001f600"


def test_plain_ascii_untouched():
    assert decode("Huskepunkter SO5.pptx") == "Huskepunkter SO5.pptx"


def test_string_table_parses_literal_non_ascii():
    """End-to-end through the table scanner, not just the decode helper."""
    parser = GWTParser.__new__(GWTParser)
    parser._parse_string_table('["øvelse.docx","\\u00e5rsplan","ren ascii"]')
    assert parser.string_table == ["øvelse.docx", "årsplan", "ren ascii"]
