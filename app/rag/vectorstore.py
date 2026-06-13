from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chromadb
from chromadb.api.models.Collection import Collection
from langchain_core.documents import Document

from app.config import get_settings

logger = logging.getLogger(__name__)


def _coerce_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure metadata is JSON-serializable for Chroma.

    Why:
    - Chroma metadata values must be primitives (str/int/float/bool) or None.
    - PDF loaders/splitters may insert non-serializable values unless we enforce it.
    """
    allowed = (str, int, float, bool)
    out: Dict[str, Any] = {}
    for k, v in (metadata or {}).items():
        if v is None or isinstance(v, allowed):
            out[k] = v
        else:
            # Convert everything else to string to preserve debuggability without breaking ingestion.
            out[k] = str(v)
    return out


@lru_cache(maxsize=1)
def _get_client() -> chromadb.PersistentClient:
    """
    Create a single persistent Chroma client.

    Why cache:
    - Avoids re-opening the underlying SQLite/duckdb resources repeatedly.
    - Keeps performance stable under API load.
    """
    settings = get_settings()
    persist_dir = settings.resolved_chroma_persist_dir()
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def _get_or_create_collection(name: str) -> Collection:
    """
    Fetch or create the collection.

    Why:
    - Explicit collection management makes behavior predictable across restarts.
    - We store embeddings explicitly (no embedding_function attached), so querying must
      also pass query_embeddings explicitly.
    """
    client = _get_client()
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


class ChromaVectorStore:
    """
    Thin wrapper around Chroma that speaks in LangChain Documents.

    Key decision:
    - We do not rely on LangChain's vectorstore wrappers to reduce dependency surface
      and keep control over persistence + metadata rules.
    """

    def __init__(self, collection_name: str):
        self._collection_name = collection_name
        self._collection = _get_or_create_collection(collection_name)

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def count(self) -> int:
        return int(self._collection.count())

    def upsert_documents(
        self,
        docs: Iterable[Document],
        embedder: Any,
    ) -> int:
        """
        Upsert chunks into Chroma.

        Requirements handled:
        - Stable IDs so re-indexing is idempotent.
        - Persistent storage (Chroma PersistentClient).
        """
        docs_list = list(docs)
        if not docs_list:
            return 0

        texts: List[str] = [d.page_content for d in docs_list]

        # Use deterministic IDs when available; fall back to a content-derived key.
        ids: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        for d in docs_list:
            md = _coerce_metadata(d.metadata or {})
            chunk_key = md.get("chunk_key")
            if isinstance(chunk_key, str) and chunk_key:
                doc_id = chunk_key
            else:
                # Fallback: still stable for same content+source combo, avoids duplicates.
                source = str(md.get("file_sha256", "")) + "|" + str(md.get("page", "")) + "|" + str(md.get("source", ""))
                doc_id = f"fallback:{hash((source, d.page_content))}"
                md["chunk_key"] = doc_id  # make future runs stable within this index

            ids.append(doc_id)
            metadatas.append(md)

        embeddings = embedder.embed_documents(texts)

        # Upsert is important: it makes ingestion idempotent (rerunning won't duplicate vectors).
        self._collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return len(ids)

    def delete_by_file_sha256(self, file_sha256: str) -> None:
        """
        Delete all chunks belonging to a given file.

        Why:
        - Enables re-upload workflows without duplicating old vectors.
        - Useful for user-controlled data lifecycle.
        """
        if not file_sha256:
            return
        self._collection.delete(where={"file_sha256": file_sha256})

    def get_chunks_by_source_page(self, source: str, page: int) -> str:
        result = self._collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        chunks = [d for d, m in zip(docs, metas) if (m or {}).get("page") is not None and int((m or {}).get("page", -1)) == page]
        return "\n\n".join(chunks)

    def delete_by_source(self, source: str) -> None:
        if not source:
            return
        self._collection.delete(where={"source": source})

    def list_sources(self) -> List[str]:
        result = self._collection.get(include=["metadatas"])
        metadatas = result.get("metadatas") or []
        seen: set[str] = set()
        for md in metadatas:
            s = (md or {}).get("source", "")
            if s and s not in seen:
                seen.add(s)
        return sorted(seen)

    def reset_collection(self) -> None:
        """
        Drop and recreate the collection.

        Why:
        - Useful for tests and local development.
        - Explicitly implemented to avoid accidental data loss elsewhere.
        """
        client = _get_client()
        try:
            client.delete_collection(name=self._collection_name)
        except Exception:
            # If collection doesn't exist yet, treat as already reset.
            pass
        self._collection = _get_or_create_collection(self._collection_name)

    def similarity_search_by_embedding(
        self,
        query_embedding: List[float],
        top_k: int,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """
        Query Chroma using a precomputed embedding.

        Returns:
        - List of (Document, distance). Lower distance is better for cosine in Chroma.

        Why return distance:
        - Enables downstream thresholding/diagnostics without re-querying.
        """
        if not query_embedding:
            return []

        res = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs_out: List[Tuple[Document, float]] = []

        # Chroma returns lists per query (we only send one query).
        documents = (res.get("documents") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]

        for text, md, dist in zip(documents, metadatas, distances):
            if not text:
                continue
            metadata = md or {}
            docs_out.append((Document(page_content=text, metadata=metadata), float(dist)))

        return docs_out

    def similarity_search(
        self,
        query: str,
        embedder: Any,
        top_k: int,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """
        Convenience wrapper: embed + search.

        Why:
        - Keeps retriever logic small and testable.
        """
        query_embedding = embedder.embed_query(query)
        return self.similarity_search_by_embedding(query_embedding=query_embedding, top_k=top_k, where=where)


def get_vectorstore() -> ChromaVectorStore:
    """
    Factory using app Settings.

    Why:
    - Central place to ensure the collection name is consistent across the app.
    - Avoids passing settings through every layer.
    """
    settings = get_settings()
    return ChromaVectorStore(collection_name=settings.chroma_collection)