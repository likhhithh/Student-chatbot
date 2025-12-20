from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import List

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

# We import the app factory (not the global `app`) so tests can isolate env + caches.
from app.api.main import create_app


def _clear_caches() -> None:
    """
    The app uses lru_cache for settings and Chroma clients.
    Tests must clear caches after changing env vars to avoid cross-test contamination.
    """
    # Local imports keep test import-time side effects minimal.
    from app.config import get_settings
    from app.rag import vectorstore as vs_mod
    from app.rag import retriever as ret_mod
    from app.rag import chain as chain_mod

    get_settings.cache_clear()
    # Chroma client is cached; needs reset when CHROMA_PERSIST_DIR changes.
    vs_mod._get_client.cache_clear()  # type: ignore[attr-defined]

    # Retriever/embedder/chain are cached singletons in-process.
    ret_mod.get_retriever.cache_clear()  # type: ignore[attr-defined]
    ret_mod._get_embedder.cache_clear()  # type: ignore[attr-defined]
    chain_mod.get_chain.cache_clear()  # type: ignore[attr-defined]
    chain_mod._load_llm_and_tokenizer.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Provide per-test isolated storage.

    Why:
    - Chroma is persistent by design; tests must not share a global on-disk DB.
    - Upload storage must be isolated to prevent interference.
    """
    uploads_dir = tmp_path / "uploads"
    chroma_dir = tmp_path / "chroma"
    collection = f"test_{uuid.uuid4().hex}"

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("UPLOADS_DIR", str(uploads_dir))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setenv("CHROMA_COLLECTION", collection)

    _clear_caches()


@pytest.fixture()
def client(isolated_env: None) -> TestClient:
    """
    Create an isolated FastAPI TestClient per test.

    Why:
    - Ensures app startup uses the per-test env vars and fresh caches.
    """
    app = create_app()
    return TestClient(app)


def test_healthz_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert isinstance(data["vectors"], int)
    assert "collection" in data


def test_upload_indexes_documents_without_real_pdf_parsing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Smoke test for /upload:
    - Avoids heavyweight model downloads by patching embeddings.
    - Avoids brittle PDF parsing by patching the loader to return a Document directly.

    This still exercises:
    - FastAPI upload handling
    - Disk persistence of the uploaded file
    - Chunking
    - Chroma upsert + count
    """
    # Patch load_pdf (as imported into app.api.main) to bypass actual PDF parsing.
    import app.api.main as api_main

    def fake_load_pdf(_: Path) -> List[Document]:
        return [
            Document(
                page_content="Ohm's law states that voltage V equals current I times resistance R: V = I * R.",
                metadata={
                    "source": "test.pdf",
                    "file_name": "test.pdf",
                    "file_path": "/tmp/test.pdf",
                    "file_sha256": "testhash",
                    "page": 1,
                },
            )
        ]

    monkeypatch.setattr(api_main, "load_pdf", fake_load_pdf)

    # Patch embeddings used by /upload to avoid downloading SentenceTransformers model.
    class DummyEmbeddings:
        def __init__(self, *_args, **_kwargs) -> None:
            # Fixed dimension; Chroma requires consistent vector lengths.
            self.dim = 8

        def embed_documents(self, texts: List[str]) -> List[List[float]]:
            out: List[List[float]] = []
            for t in texts:
                # Deterministic pseudo-embedding based on text length and char sums.
                s = sum(ord(c) for c in t) % 997
                base = float((len(t) + s) % 101) / 101.0
                out.append([base + (i * 0.001) for i in range(self.dim)])
            return out

        def embed_query(self, text: str) -> List[float]:
            s = sum(ord(c) for c in text) % 997
            base = float((len(text) + s) % 101) / 101.0
            return [base + (i * 0.001) for i in range(self.dim)]

    monkeypatch.setattr(api_main, "SentenceTransformerEmbeddings", DummyEmbeddings)

    # Upload any bytes; loader is patched so content doesn't matter.
    fake_pdf_bytes = b"%PDF-1.4\n%Fake PDF for tests\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    files = [("files", ("test.pdf", fake_pdf_bytes, "application/pdf"))]

    r = client.post("/upload", files=files)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["pages_loaded"] == 1
    assert data["chunks_indexed"] >= 1
    assert data["vector_count"] >= 1
    assert data["stored_files"] and data["stored_files"][0].endswith(".pdf")


def test_ask_returns_idk_with_mocked_chain(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    /ask should return an answer and session_id.
    We mock the chain to avoid loading LLM weights during tests.
    """
    import app.api.main as api_main
    from app.rag.chain import AnswerResult, IDK

    class DummyChain:
        def answer(self, session_id: str, question: str) -> AnswerResult:
            # Force the strict fallback response.
            return AnswerResult(answer=IDK, sources=[])

        def clear_session(self, session_id: str) -> None:
            return None

    monkeypatch.setattr(api_main, "get_chain", lambda: DummyChain())

    r = client.post("/ask", json={"session_id": "sess123", "question": "What is Ohm's law?"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == "sess123"
    assert data["answer"] == "I don't know"
    assert data["sources"] == []


def test_clear_session_calls_chain(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.main as api_main

    called = {"sid": None}

    class DummyChain:
        def answer(self, session_id: str, question: str):
            raise RuntimeError("Not used in this test")

        def clear_session(self, session_id: str) -> None:
            called["sid"] = session_id

    monkeypatch.setattr(api_main, "get_chain", lambda: DummyChain())

    sid = "to_clear_1"
    r = client.post("/session/clear", params={"session_id": sid})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cleared"] is True
    assert data["session_id"] == sid
    assert called["sid"] == sid