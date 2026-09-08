"""Modular document parsers (V1). PRD section 13.

Supported formats: PDF, DOC/DOCX, XLS/XLSX, PPT/PPTX, TXT, CSV, JSON,
common image formats (metadata), ZIP (metadata listing) and folders.
Each parser returns {"extracted_text", "structure", "meta"} so new formats
can be added without touching callers.
"""
from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

# Optional heavy dependencies, imported lazily so the server still boots
# even when one of them is missing on a minimal install.
try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None

try:
    import docx  # type: ignore
except Exception:  # pragma: no cover
    docx = None

try:
    import openpyxl  # type: ignore
except Exception:  # pragma: no cover
    openpyxl = None

try:
    from pptx import Presentation  # type: ignore
except Exception:  # pragma: no cover
    Presentation = None

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None

TEXT_EXTENSIONS = {".txt", ".md", ".log", ".rtf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

MAX_TEXT_CHARS = 50_000


def parse_file(path: Path) -> dict:
    """Parse a supported file. Returns extracted text + structure + meta.

    Unsupported formats return an explicit "unsupported" structure so the
    caller can report a natural-language message instead of crashing.
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _parse_pdf(path)
        if suffix in {".doc", ".docx"}:
            return _parse_docx(path)
        if suffix in {".xls", ".xlsx"}:
            return _parse_xlsx(path)
        if suffix in {".ppt", ".pptx"}:
            return _parse_pptx(path)
        if suffix in TEXT_EXTENSIONS:
            return _parse_text(path)
        if suffix == ".csv":
            return _parse_csv(path)
        if suffix == ".json":
            return _parse_json(path)
        if suffix == ".zip":
            return _parse_zip(path)
        if suffix in IMAGE_EXTENSIONS:
            return _parse_image(path)
    except Exception as exc:  # noqa: BLE001 - parser must never crash the agent
        return {"extracted_text": "", "structure": "error", "meta": {}, "error": str(exc)}
    return {
        "extracted_text": "",
        "structure": "unsupported",
        "meta": {},
        "error": f"Format {suffix or 'tanpa ekstensi'} belum didukung parser ini.",
    }


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_TEXT_CHARS else text[:MAX_TEXT_CHARS] + "\n…[dipotong]"


def _parse_text(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"extracted_text": _truncate(text), "structure": "text", "meta": {"chars": len(text)}}


def _parse_csv(path: Path) -> dict:
    rows: list[list[str]] = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.reader(handle):
            rows.append(row)
            if len(rows) >= 200:
                break
    text = "\n".join(",".join(r) for r in rows)
    return {
        "extracted_text": _truncate(text),
        "structure": "csv",
        "meta": {"rows_preview": len(rows)},
    }


def _parse_json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(raw, indent=2, ensure_ascii=False)
    return {"extracted_text": _truncate(text), "structure": "json", "meta": {}}


def _parse_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        total = len(names)
        size = sum(max(info.file_size, 0) for info in archive.infolist())
    return {
        "extracted_text": "",
        "structure": "zip",
        "meta": {"entries": names[:200], "entry_count": total, "uncompressed_size": size},
    }


def _parse_pdf(path: Path) -> dict:
    if PdfReader is None:
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Parser PDF tidak tersedia."}
    reader = PdfReader(str(path))
    pages_text: list[str] = []
    for page in reader.pages[:50]:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    text = "\n".join(pages_text)
    return {
        "extracted_text": _truncate(text),
        "structure": "pdf",
        "meta": {"pages": len(reader.pages), "pages_extracted": len(pages_text)},
    }


def _parse_docx(path: Path) -> dict:
    if docx is None:
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Parser DOCX tidak tersedia."}
    if path.suffix.lower() == ".doc":
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Format .doc lama belum didukung; gunakan .docx."}
    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs]
    tables = []
    for table in document.tables[:10]:
        for row in table.rows[:50]:
            tables.append(" | ".join(cell.text for cell in row.cells))
    text = "\n".join(paragraphs + tables)
    return {
        "extracted_text": _truncate(text),
        "structure": "docx",
        "meta": {"paragraphs": len(paragraphs), "tables": len(document.tables)},
    }


def _parse_xlsx(path: Path) -> dict:
    if openpyxl is None:
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Parser XLSX tidak tersedia."}
    if path.suffix.lower() == ".xls":
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Format .xls lama belum didukung; gunakan .xlsx."}
    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    chunks: list[str] = []
    sheet_names = workbook.sheetnames[:5]
    for sheet_name in sheet_names:
        sheet = workbook[sheet_name]
        chunks.append(f"[Sheet: {sheet_name}]")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= 100:
                chunks.append("…[baris berikutnya dipotong]")
                break
            values = ["" if v is None else str(v) for v in row]
            if any(values):
                chunks.append(" | ".join(values))
    workbook.close()
    return {
        "extracted_text": _truncate("\n".join(chunks)),
        "structure": "xlsx",
        "meta": {"sheets": sheet_names},
    }


def _parse_pptx(path: Path) -> dict:
    if Presentation is None:
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Parser PPTX tidak tersedia."}
    if path.suffix.lower() == ".ppt":
        return {"extracted_text": "", "structure": "unsupported", "meta": {}, "error": "Format .ppt lama belum didukung; gunakan .pptx."}
    prs = Presentation(str(path))
    chunks: list[str] = []
    for idx, slide in enumerate(prs.slides[:50]):
        chunks.append(f"[Slide {idx + 1}]")
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                chunks.append(shape.text)
    return {
        "extracted_text": _truncate("\n".join(chunks)),
        "structure": "pptx",
        "meta": {"slides": len(prs.slides)},
    }


def _parse_image(path: Path) -> dict:
    if Image is None:
        return {"extracted_text": "", "structure": "image", "meta": {}, "error": "Parser gambar tidak tersedia."}
    with Image.open(path) as img:
        meta = {
            "format": img.format,
            "width": img.width,
            "height": img.height,
            "mode": img.mode,
        }
    return {"extracted_text": "", "structure": "image", "meta": meta}
