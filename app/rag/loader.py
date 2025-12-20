from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document
from pypdf import PdfReader

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def _is_pdf(path: Path) -> bool:
    # Defensive check: users can upload arbitrary files; we only process PDFs.
    return path.is_file() and path.suffix.lower() == ".pdf"


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """
    Compute a stable content hash for deduplication/traceability.

    Why:
    - Persistent vector stores benefit from stable identifiers and metadata.
    - Hashing avoids relying on filenames alone (users can upload duplicates).
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _clean_text(text: str) -> str:
    """
    Normalize extracted PDF text.

    Why:
    - PDF extraction often includes irregular newlines and spacing.
    - Normalization improves chunking quality and retrieval consistency.
    """
    text = text.replace("\x00", " ")  # Rare in PDFs; can break downstream tokenization.
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def load_pdf(path: Path) -> list[Document]:
    """
    Load a single PDF into per-page LangChain Documents.

    Design choice (per-page docs):
    - Keeps source attribution precise (page numbers).
    - Helps later chunking preserve locality (chunker can merge/split as needed).
    """
    if not _is_pdf(path):
        raise ValueError(f"Not a PDF file: {path}")

    file_hash = _sha256_file(path)
    docs: list[Document] = []

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        # Fail loudly: better to inform the user a file is unreadable than silently ignore it.
        raise RuntimeError(f"Failed to read PDF '{path.name}': {e}") from e

    # Some PDFs are encrypted; pypdf may require a password to proceed.
    if getattr(reader, "is_encrypted", False):
        try:
            # Attempt empty password; many PDFs are "encrypted" but openable.
            reader.decrypt("")  # type: ignore[attr-defined]
        except Exception as e:
            raise RuntimeError(f"Encrypted PDF not supported without password: {path.name}") from e

    for page_idx, page in enumerate(reader.pages):
        try:
            raw = page.extract_text() or ""
        except Exception:
            # Extraction can fail for a page; we continue so usable pages still index.
            logger.warning("Failed to extract text from %s page %d", path.name, page_idx + 1)
            continue

        cleaned = _clean_text(raw)
        if not cleaned:
            continue

        docs.append(
            Document(
                page_content=cleaned,
                metadata={
                    "source": path.name,  # human-friendly display
                    "file_name": path.name,
                    "file_path": str(path.resolve()),
                    "file_sha256": file_hash,
                    "page": page_idx + 1,  # 1-based indexing for user-friendly citations
                },
            )
        )

    return docs


def load_pdfs(paths: Iterable[Path]) -> list[Document]:
    """
    Load multiple PDFs into Documents.

    Why:
    - Keeps ingestion logic centralized and testable.
    - Lets the API layer pass either selected files or "all uploads".
    """
    all_docs: list[Document] = []
    for p in paths:
        if not _is_pdf(p):
            logger.info("Skipping non-PDF file: %s", p)
            continue
        all_docs.extend(load_pdf(p))
    return all_docs


def load_pdfs_from_dir(uploads_dir: Path) -> list[Document]:
    """
    Load all PDFs from a directory (non-recursive).

    Why non-recursive:
    - Upload directories are typically flat; recursion increases risk of indexing
      unintended files when deployed.
    """
    uploads_dir = uploads_dir.resolve()
    if not uploads_dir.exists():
        return []

    pdfs = sorted([p for p in uploads_dir.iterdir() if _is_pdf(p)])
    return load_pdfs(pdfs)