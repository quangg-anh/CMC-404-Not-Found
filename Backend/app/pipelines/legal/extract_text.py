"""Extract raw text from uploaded legal files (PDF / DOCX / TXT / HTML).

Used by the ingest pipeline to turn a binary file (fetched from MinIO) into plain text that the
``LegalParser`` can split into Điều/Khoản. Every extractor is best-effort: on failure it returns
an empty string and logs a warning, so a single bad file never crashes ingest.
"""
from __future__ import annotations

import io
import logging
import re

logger = logging.getLogger(__name__)


def extract_text(data: bytes, filename: str = "", mime: str = "") -> str:
    """Dispatch to the right extractor based on filename extension / MIME type."""
    if not data:
        return ""
    name = (filename or "").lower()
    m = (mime or "").lower()
    if name.endswith(".pdf") or "pdf" in m:
        return _from_pdf(data)
    if name.endswith(".docx") or "wordprocessingml" in m:
        return _from_docx(data)
    if name.endswith((".html", ".htm")) or "html" in m:
        return _strip_html(_decode(data))
    return _decode(data)


def _from_pdf(data: bytes) -> str:
    """Extract text from a PDF: try the text layer first, then OCR for scanned/image PDFs."""
    text = ""
    try:
        import pdfplumber

        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_text: PDF text-layer extraction failed: %s", exc)

    # A scanned/image-only PDF has (almost) no text layer → fall back to OCR.
    if len(text) >= 40:
        return text
    ocr = _ocr_pdf(data)
    return ocr or text


def _ocr_pdf(data: bytes) -> str:
    """OCR a scanned PDF using PyMuPDF (rasterize) + pytesseract with Vietnamese ('vie').

    Best-effort and fully optional: if PyMuPDF / pytesseract / the Tesseract binary or the 'vie'
    language pack are missing, log a hint and return "" so ingest degrades gracefully (the caller
    then flags needs_review and asks the operator to paste the text).
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_text: OCR libs unavailable (%s); scanned PDF cannot be read.", exc)
        return ""
    try:
        parts: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    parts.append(pytesseract.image_to_string(img, lang="vie"))
                except Exception:  # noqa: BLE001 - 'vie' pack may be missing; fall back to default
                    parts.append(pytesseract.image_to_string(img))
        return "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_text: OCR failed (Tesseract binary/lang missing?): %s", exc)
        return ""


def _from_docx(data: bytes) -> str:
    try:
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_text: DOCX extraction failed: %s", exc)
        return ""


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return data.decode("utf-8", errors="ignore")


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()
