"""Privacy-conscious PDF CV extraction.

The parser accepts bytes only and never writes the uploaded document to disk.
Limits reduce accidental resource exhaustion from large or unusually long PDFs.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


MAX_CV_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_CV_PAGES = 15
MAX_CV_TEXT_CHARS = 100_000


class CVProcessingError(ValueError):
    """A safe, user-displayable explanation for why a CV could not be processed."""


@dataclass(frozen=True)
class CVExtraction:
    text: str
    page_count: int
    truncated: bool


def extract_pdf_text(pdf_bytes: bytes) -> CVExtraction:
    """Extract text from an in-memory PDF with strict size/page/output limits."""
    if not isinstance(pdf_bytes, (bytes, bytearray)) or not pdf_bytes:
        raise CVProcessingError("El archivo está vacío o no se ha podido leer.")
    if len(pdf_bytes) > MAX_CV_UPLOAD_BYTES:
        raise CVProcessingError("El PDF supera el límite de 5 MB.")

    try:
        reader = PdfReader(BytesIO(bytes(pdf_bytes)), strict=False)
        if reader.is_encrypted:
            raise CVProcessingError(
                "El PDF está protegido con contraseña. Sube una copia desbloqueada."
            )
        page_count = len(reader.pages)
        if page_count < 1:
            raise CVProcessingError("El PDF no contiene páginas.")
        if page_count > MAX_CV_PAGES:
            raise CVProcessingError(
                f"El PDF tiene {page_count} páginas; el máximo admitido es {MAX_CV_PAGES}."
            )

        chunks: list[str] = []
        remaining = MAX_CV_TEXT_CHARS
        truncated = False
        for page in reader.pages:
            if remaining <= 0:
                truncated = True
                break
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            if len(page_text) > remaining:
                chunks.append(page_text[:remaining])
                remaining = 0
                truncated = True
                break
            chunks.append(page_text)
            remaining -= len(page_text)
    except CVProcessingError:
        raise
    except Exception as exc:
        # Do not echo parser exception text: malformed PDFs can contain user data.
        raise CVProcessingError(
            "No se ha podido leer el PDF. Prueba con un PDF válido y sin protección."
        ) from exc

    text = "\n".join(chunks).strip()
    if not text:
        raise CVProcessingError(
            "No se ha podido extraer texto del PDF. Puede ser un documento escaneado."
        )
    return CVExtraction(text=text, page_count=page_count, truncated=truncated)
