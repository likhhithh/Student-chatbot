from __future__ import annotations

from typing import Iterable, List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def build_text_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    """
    Create a production-friendly text splitter.

    Why RecursiveCharacterTextSplitter:
    - Fast and deterministic (good for CPU-only).
    - Works well on messy PDF text by trying multiple separators before falling back.
    - Character-based sizing is predictable; token-based splitters can vary across models.
    """
    if chunk_overlap >= chunk_size:
        # Avoid degenerate behavior where overlap prevents progress.
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # Ordered from "best" semantic boundaries to worst; helps preserve coherence.
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ": ", ", ", " ", ""],
        add_start_index=True,  # Enables traceability when debugging retrieval.
    )


def chunk_documents(
    docs: Iterable[Document],
    chunk_size: int,
    chunk_overlap: int,
) -> List[Document]:
    """
    Split Documents into smaller chunks, preserving metadata.

    Key decision:
    - We keep original metadata (source/page/hash) to support citations and dedup.
    - We add chunk-level fields for stable IDs downstream.
    """
    splitter = build_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    input_docs = list(docs)
    if not input_docs:
        return []

    chunks = splitter.split_documents(input_docs)

    # Attach a deterministic chunk index per (file_sha256, page) group to support stable IDs.
    # We do it post-split because the splitter creates new Document objects.
    counters: dict[tuple[str, int], int] = {}
    out: list[Document] = []

    for d in chunks:
        file_hash = str(d.metadata.get("file_sha256", ""))
        page = int(d.metadata.get("page", -1))
        key = (file_hash, page)

        idx = counters.get(key, 0)
        counters[key] = idx + 1

        md = dict(d.metadata)
        md["chunk_index"] = idx
        # Helpful for filtering/debugging, and for building stable IDs for the vectorstore.
        md["chunk_key"] = f"{file_hash}:{page}:{idx}"

        out.append(Document(page_content=d.page_content, metadata=md))

    return out