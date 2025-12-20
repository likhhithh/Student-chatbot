from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document

from app.config import get_settings
from app.rag.embeddings import EmbeddingConfig, SentenceTransformerEmbeddings
from app.rag.vectorstore import ChromaVectorStore, get_vectorstore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrieverConfig:
    top_k: int
    # Hard cap to keep prompts bounded on CPU-only deployments.
    # We cap by characters because it's fast and model-agnostic.
    max_context_chars: int = 12_000


@dataclass(frozen=True)
class RetrievedChunk:
    document: Document
    distance: float  # Chroma cosine distance (lower is better)
    citation: str    # Human-friendly source reference


def _make_citation(doc: Document) -> str:
    src = doc.metadata.get("source") or doc.metadata.get("file_name") or "unknown"
    page = doc.metadata.get("page")
    if page is None:
        return f"{src}"
    return f"{src} (page {page})"


def _format_context_block(idx: int, doc: Document) -> str:
    """
    Format a single retrieved chunk for the prompt context.

    Why this structure:
    - Bracketed IDs make it easy for the LLM to reference specific chunks.
    - Including source/page supports trust and debugging in the UI.
    """
    citation = _make_citation(doc)
    text = doc.page_content.strip()
    return f"[{idx}] SOURCE: {citation}\n{text}"


def _truncate_context(blocks: List[str], max_chars: int) -> str:
    """
    Truncate context to a fixed character budget.

    Why:
    - Prevents worst-case latency/memory spikes on CPU.
    - Keeps generation stable for smaller models.
    """
    if max_chars <= 0:
        return ""

    out: List[str] = []
    used = 0
    for b in blocks:
        # +2 accounts for the blank line separator we add between blocks.
        add_len = len(b) + (2 if out else 0)
        if used + add_len > max_chars:
            break
        out.append(b)
        used += add_len
    return "\n\n".join(out).strip()


class RAGRetriever:
    """
    Retrieves top-k relevant chunks from Chroma.

    Design choices:
    - Retriever returns both formatted context and raw chunks so the chain/UI can
      display citations and debug retrieval.
    - No hard similarity threshold by default because distances vary by domain/model.
      We only treat "no results" as no knowledge; the prompt enforces "I don't know".
    """

    def __init__(
        self,
        vectorstore: ChromaVectorStore,
        embedder: SentenceTransformerEmbeddings,
        config: RetrieverConfig,
    ) -> None:
        self._vs = vectorstore
        self._embedder = embedder
        self._config = config

    def retrieve(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        if not query.strip():
            return []

        results: List[Tuple[Document, float]] = self._vs.similarity_search(
            query=query,
            embedder=self._embedder,
            top_k=self._config.top_k,
            where=where,
        )

        out: List[RetrievedChunk] = []
        seen_keys: set[str] = set()

        for doc, dist in results:
            # Deduplicate by chunk_key when possible; this prevents repeated context blocks.
            chunk_key = str(doc.metadata.get("chunk_key") or "")
            if chunk_key and chunk_key in seen_keys:
                continue
            if chunk_key:
                seen_keys.add(chunk_key)

            out.append(
                RetrievedChunk(
                    document=doc,
                    distance=dist,
                    citation=_make_citation(doc),
                )
            )

        return out

    def build_context(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, List[RetrievedChunk]]:
        """
        Retrieve and format context for the QA prompt.
        """
        chunks = self.retrieve(query=query, where=where)
        if not chunks:
            return "", []

        blocks = [_format_context_block(i + 1, c.document) for i, c in enumerate(chunks)]
        context = _truncate_context(blocks, max_chars=self._config.max_context_chars)
        return context, chunks


@lru_cache(maxsize=1)
def _get_embedder() -> SentenceTransformerEmbeddings:
    """
    Cached embedder instance.

    Why cache:
    - Embedding model load dominates startup on CPU.
    - Both ingestion and retrieval should reuse the same loaded model.
    """
    settings = get_settings()
    return SentenceTransformerEmbeddings(EmbeddingConfig(model_name=settings.embedding_model_name))


@lru_cache(maxsize=1)
def get_retriever() -> RAGRetriever:
    """
    App-level retriever factory.

    Why:
    - Ensures consistent top_k and persistent Chroma collection across imports.
    - Avoids rebuilding heavy objects per-request.
    """
    settings = get_settings()
    vs = get_vectorstore()
    embedder = _get_embedder()
    config = RetrieverConfig(top_k=settings.top_k)
    return RAGRetriever(vectorstore=vs, embedder=embedder, config=config)