from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pdfplumber

try:
    import fitz
except ImportError:  # pragma: no cover - optional runtime dependency
    fitz = None

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # pragma: no cover - optional runtime dependency
    RapidOCR = None


def normalize_text(text: str) -> str:
    cleaned = text.replace("\x00", " ")
    replacements = {
        "USO": "USD",
        "U5D": "USD",
        "S$": "SGD ",
        "O00": "000",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()


def assess_text_quality(text: str) -> str:
    if not text:
        return "empty"
    alpha_chars = sum(char.isalpha() for char in text)
    digit_chars = sum(char.isdigit() for char in text)
    useful_chars = alpha_chars + digit_chars
    if useful_chars < 80:
        return "low"
    return "good"


def infer_document_type(text: str) -> str:
    lowered = text.lower()
    if any(
        keyword in lowered
        for keyword in (
            "insurance payment",
            "premium only",
            "policy no",
            "policy number",
            "deposit account",
            "credit advice",
            "bank deposit",
            "ocbc",
        )
    ):
        return "payment proof"
    if any(keyword in lowered for keyword in ("mt103", "telegraphic transfer", "remittance", "swift", "beneficiary")):
        return "payment proof"
    if any(keyword in lowered for keyword in ("income tax", "notice of assessment", "salary", "payslip")):
        return "income proof"
    if any(keyword in lowered for keyword in ("net worth", "assets", "holdings", "portfolio", "statement")):
        return "net worth proof"
    return "unknown"


def _extract_native_text(file_bytes: bytes) -> str:
    text = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text.append(page.extract_text() or "")
    return normalize_text("\n".join(text))


def _ocr_reader():
    if RapidOCR is None:
        return None
    return RapidOCR()


def _extract_pdf_ocr_text(file_bytes: bytes) -> str:
    reader = _ocr_reader()
    if fitz is None or reader is None:
        return ""

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            result, _ = reader(pix.tobytes("png"))
            if not result:
                continue
            page_text = " ".join(item[1] for item in result)
            pages.append(page_text)
    finally:
        doc.close()
    return normalize_text("\n".join(pages))


def _extract_image_ocr_text(file_bytes: bytes) -> str:
    reader = _ocr_reader()
    if reader is None:
        return ""

    result, _ = reader(file_bytes)
    if not result:
        return ""
    return normalize_text(" ".join(item[1] for item in result))


def _is_pdf(uploaded_file: Any) -> bool:
    filename = getattr(uploaded_file, "name", "").lower()
    content_type = getattr(uploaded_file, "type", "") or ""
    return filename.endswith(".pdf") or "pdf" in content_type.lower()


def analyze_document(uploaded_file: Any) -> dict:
    file_bytes = uploaded_file.getvalue()
    is_pdf = _is_pdf(uploaded_file)
    native_text = _extract_native_text(file_bytes) if is_pdf else ""
    native_quality = assess_text_quality(native_text)
    warnings = []

    text = native_text
    extraction_method = "native PDF text" if is_pdf else "image OCR"

    if native_quality != "good":
        ocr_text = _extract_pdf_ocr_text(file_bytes) if is_pdf else _extract_image_ocr_text(file_bytes)
        if ocr_text:
            text = ocr_text if len(ocr_text) >= len(native_text) else native_text
            extraction_method = "OCR fallback" if is_pdf else "image OCR"
            warnings.append(
                "OCR fallback used because native text extraction was limited."
                if is_pdf
                else "Image OCR used for this uploaded receipt."
            )
        elif native_quality == "empty":
            warnings.append("No extractable text found. OCR fallback was unavailable or did not return text.")

    quality = assess_text_quality(text)
    if quality == "low":
        warnings.append("Low-confidence text extraction. Validate numbers manually.")
    elif quality == "empty":
        warnings.append("Document text is empty after extraction.")

    return {
        "filename": uploaded_file.name,
        "text": text,
        "text_quality": quality,
        "extraction_method": extraction_method,
        "document_type": infer_document_type(text),
        "warnings": warnings,
        "confidence": 0.9 if quality == "good" else 0.55 if quality == "low" else 0.2,
        "evidence": [],
    }


def analyze_documents(uploaded_files: list[Any]) -> list[dict]:
    return [analyze_document(file) for file in uploaded_files]
