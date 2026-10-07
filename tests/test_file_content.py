"""
Offline tests for readable_file: a load_lesson_file result must reach Claude as
readable text or an image, never as raw base64.
"""
import base64
import json
import io

from docx import Document

from file_content import MAX_TEXT_CHARS, readable_file


def loaded(file_name, data, content_type="application/octet-stream"):
    """A successful load_lesson_file result. Studie+ serves every file as octet-stream."""
    return {
        "success": True,
        "file_name": file_name,
        "content": base64.b64encode(data).decode("ascii"),
        "content_type": content_type,
        "size": len(data),
        "is_text": False,
    }


def minimal_pdf(text):
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def docx_bytes(*paragraphs):
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def single_dict(result):
    assert len(result.content) == 1
    return json.loads(result.content[0].text)


def test_pdf_text_is_extracted():
    body = single_dict(readable_file(loaded("opgave.pdf", minimal_pdf("Vaelg opgave 1, 2 eller 5"))))
    assert body["success"]
    assert "Vaelg opgave 1, 2 eller 5" in body["content"]
    assert body["content_type"] == "application/pdf"


def test_docx_text_is_extracted():
    body = single_dict(readable_file(loaded("opgave.docx", docx_bytes("Eventyr", "Læs H.C. Andersen"))))
    assert body["success"]
    assert "Eventyr" in body["content"]
    assert "Læs H.C. Andersen" in body["content"]


def test_text_file_served_as_octet_stream_is_decoded():
    body = single_dict(readable_file(loaded("noter.txt", "Æbler og øl".encode("utf-8"))))
    assert body["content"] == "Æbler og øl"


def test_image_is_returned_as_image_content():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    result = readable_file(loaded("figur.png", png))
    assert [c.type for c in result.content] == ["text", "image"]
    assert result.content[1].mimeType == "image/png"
    assert base64.b64decode(result.content[1].data) == png


def test_zip_is_refused_with_hint_to_download():
    body = single_dict(readable_file(loaded("Eventyr.zip", b"PK\x03\x04")))
    assert not body["success"]
    assert "download_lesson_file" in body["error"]
    assert "content" not in body


def test_pdf_without_text_is_refused():
    body = single_dict(readable_file(loaded("scannet.pdf", minimal_pdf(""))))
    assert not body["success"]
    assert "scannet" in body["error"]


def test_long_text_is_truncated():
    body = single_dict(readable_file(loaded("lang.txt", b"a" * (MAX_TEXT_CHARS + 10))))
    assert body["truncated"]
    assert body["total_chars"] == MAX_TEXT_CHARS + 10
    assert len(body["content"]) == MAX_TEXT_CHARS


def test_failed_load_is_passed_through():
    # too_large comes from studieplus-api when the file exceeds its size limit.
    failed = {"success": False, "too_large": True, "file_name": "stor.zip", "error": "File is larger than 20 MB"}
    assert single_dict(readable_file(failed)) == failed
