from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.rag.bedrock_embeddings import get_bedrock_embedder
from app.rag.chain import AnswerResult, get_chain
from app.rag.chunking import chunk_documents
from app.rag.loader import load_image, load_pdf
from app.rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)


_FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9.\-_ ]+")
_ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
_IMAGE_EXTS   = {".png", ".jpg", ".jpeg", ".webp"}

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = _FILENAME_SAFE_RE.sub("", base).strip()
    base = base.replace(" ", "_")
    return base or f"upload_{uuid.uuid4().hex}.bin"


def _unique_path(dir_path: Path, filename: str) -> Path:
    """
    Create a unique path without overwriting existing files.

    Why:
    - Users can upload files with same names.
    - We want persistence across restarts; overwriting could silently change indexed content.
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    candidate = dir_path / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(1, 10_000):
        alt = dir_path / f"{stem}__{i}{suffix}"
        if not alt.exists():
            return alt

    # Extremely unlikely; indicates directory is polluted or adversarial uploads.
    raise RuntimeError("Unable to allocate unique filename for upload.")


def _save_upload_file(upload: UploadFile, uploads_dir: Path) -> Path:
    safe_name = _sanitize_filename(upload.filename or "document.pdf")
    if Path(safe_name).suffix.lower() not in _ALLOWED_EXTS:
        safe_name = f"{safe_name}.pdf"

    out_path = _unique_path(uploads_dir, safe_name)

    # Stream to disk in chunks to keep memory usage low.
    with out_path.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    return out_path


class UploadResponse(BaseModel):
    stored_files: List[str] = Field(..., description="Filenames stored in data/uploads/")
    pages_loaded: int = Field(..., ge=0, description="Total PDF pages successfully extracted")
    chunks_indexed: int = Field(..., ge=0, description="Total chunks embedded and upserted into ChromaDB")
    vector_count: int = Field(..., ge=0, description="Current total vectors in the collection")


class AskRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="Client session identifier for chat memory. If omitted, server creates one.",
    )
    question: str = Field(..., min_length=1, description="User question")
    user_context: Optional[str] = Field(
        default=None,
        description="Long-term memory context injected from the client (recent topics, preferences).",
    )


class RestoreRequest(BaseModel):
    session_id: str
    messages: List[Dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]


class AskResponse(BaseModel):
    session_id: str = Field(..., description="Session id used for this conversation")
    answer: str = Field(..., description="Assistant answer (or 'I don't know')")
    sources: List[str] = Field(default_factory=list, description="Unique source citations used")


class ClearSessionResponse(BaseModel):
    session_id: str
    cleared: bool


def create_app() -> FastAPI:
    settings = get_settings()

    logging.basicConfig(
        level=logging.DEBUG if settings.environment == "dev" else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(title=settings.app_name)

    # Serve React SPA — always register routes; log clearly if static dir is missing
    logger.info("Static dir: %s (exists=%s)", _STATIC_DIR, _STATIC_DIR.exists())
    if _STATIC_DIR.exists():
        _assets_dir = _STATIC_DIR / "assets"
        if _assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    @app.head("/", include_in_schema=False)
    def serve_ui() -> FileResponse:
        index = _STATIC_DIR / "index.html"
        if not index.exists():
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Frontend not built", "static_dir": str(_STATIC_DIR)}, status_code=503)
        return FileResponse(str(index))

    # CORS is required when Streamlit and FastAPI are served from different origins.
    origins = settings.cors_origins_list()
    if origins == ["*"]:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,  # credentials + wildcard is not allowed by browsers
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        vs = get_vectorstore()
        return {
            "status": "ok",
            "environment": settings.environment,
            "collection": vs.collection_name,
            "vectors": vs.count(),
        }

    @app.post("/upload", response_model=UploadResponse)
    async def upload_pdfs(
        files: List[UploadFile] = File(...),
        session_id: Optional[str] = Form(None),
    ) -> UploadResponse:
        """
        Upload one or more PDFs, extract text, chunk, embed, and upsert into ChromaDB.
        """
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded.")

        uploads_dir = settings.resolved_uploads_dir()
        vs = get_vectorstore()
        embedder = get_bedrock_embedder()

        stored_files: List[str] = []
        total_pages = 0
        total_chunks = 0

        # Save and ingest sequentially to keep CPU/memory predictable on small instances.
        # (Parallel embedding can saturate CPU and degrade latency for other requests.)
        for upload in files:
            # Validate extension — content_type is not trustworthy.
            original_name = upload.filename or "document.pdf"
            file_ext = Path(original_name).suffix.lower()
            if file_ext not in _ALLOWED_EXTS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type '{file_ext}'. Allowed: PDF, PNG, JPG, JPEG, WEBP.",
                )

            try:
                saved_path = await run_in_threadpool(_save_upload_file, upload, uploads_dir)
            except Exception as e:
                logger.exception("Failed to save upload: %s", e)
                raise HTTPException(status_code=500, detail="Failed to save uploaded file.") from e
            finally:
                try:
                    upload.file.close()
                except Exception:
                    pass

            stored_files.append(saved_path.name)

            # Route to the correct loader based on extension.
            is_image = saved_path.suffix.lower() in _IMAGE_EXTS
            try:
                if is_image:
                    page_docs = await run_in_threadpool(load_image, saved_path)
                else:
                    page_docs = await run_in_threadpool(load_pdf, saved_path)
            except Exception as e:
                logger.exception("Failed to load %s: %s", saved_path.name, e)
                label = "image" if is_image else "PDF"
                raise HTTPException(status_code=400, detail=f"Failed to read {label}: {saved_path.name}") from e

            total_pages += len(page_docs)

            # Chunk
            chunks = await run_in_threadpool(
                chunk_documents,
                page_docs,
                settings.chunk_size,
                settings.chunk_overlap,
            )

            if not chunks:
                # Don't index empty docs; keep it explicit for user feedback.
                continue

            # Tag every chunk with session_id so retrieval can be scoped per conversation.
            if session_id:
                for doc in chunks:
                    doc.metadata["session_id"] = session_id

            # Upsert into Chroma (embed + store)
            upserted = await run_in_threadpool(vs.upsert_documents, chunks, embedder)
            total_chunks += upserted

        return UploadResponse(
            stored_files=stored_files,
            pages_loaded=total_pages,
            chunks_indexed=total_chunks,
            vector_count=vs.count(),
        )

    @app.post("/ask", response_model=AskResponse)
    async def ask(req: AskRequest) -> AskResponse:
        """
        Ask a question. The system answers strictly from indexed documents,
        otherwise returns: "I don't know".
        """
        session_id = (req.session_id or "").strip() or uuid.uuid4().hex
        question = (req.question or "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question cannot be empty.")

        chain = get_chain()
        try:
            result: AnswerResult = await run_in_threadpool(
                chain.answer, session_id, question, req.user_context
            )
        except Exception as e:
            logger.exception("Failed to answer question: %s", e)
            raise HTTPException(status_code=500, detail="Failed to generate an answer.") from e

        return AskResponse(session_id=session_id, answer=result.answer, sources=result.sources)

    @app.post("/ask/stream")
    async def ask_stream(req: AskRequest) -> StreamingResponse:
        """Stream answer tokens via Server-Sent Events."""
        session_id = (req.session_id or "").strip() or uuid.uuid4().hex
        question = (req.question or "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question cannot be empty.")

        chain = get_chain()
        loop = asyncio.get_event_loop()
        q: asyncio.Queue = asyncio.Queue()

        def producer() -> None:
            try:
                for item in chain.answer_stream(session_id, question, req.user_context):
                    loop.call_soon_threadsafe(q.put_nowait, item)
            except Exception as exc:
                loop.call_soon_threadsafe(q.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=producer, daemon=True).start()

        async def event_stream():
            from app.rag.chain import AnswerResult
            while True:
                item = await q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    yield f"data: {json.dumps({'error': str(item)})}\n\n"
                    break
                if isinstance(item, str):
                    yield f"data: {json.dumps({'token': item})}\n\n"
                elif isinstance(item, AnswerResult):
                    yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'sources': item.sources, 'confidence': item.confidence, 'followups': item.followups})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/session/restore")
    async def restore_session(req: RestoreRequest) -> Dict[str, Any]:
        """Restore past messages into the server-side session memory."""
        sid = (req.session_id or "").strip()
        if not sid:
            raise HTTPException(status_code=400, detail="session_id is required")
        chain = get_chain()
        await run_in_threadpool(chain.restore_session, sid, req.messages)
        return {"session_id": sid, "restored": len(req.messages)}

    @app.post("/session/clear", response_model=ClearSessionResponse)
    async def clear_session(session_id: str) -> ClearSessionResponse:
        """
        Clear server-side chat memory for a session.

        Why endpoint exists:
        - Makes the UI "New chat" button reliable.
        """
        sid = (session_id or "").strip()
        if not sid:
            raise HTTPException(status_code=400, detail="session_id is required")

        chain = get_chain()
        await run_in_threadpool(chain.clear_session, sid)
        return ClearSessionResponse(session_id=sid, cleared=True)

    class DocumentInfo(BaseModel):
        filename: str
        size_kb: float
        indexed: bool

    @app.get("/documents", response_model=List[DocumentInfo])
    def list_documents() -> List[DocumentInfo]:
        uploads_dir = settings.resolved_uploads_dir()
        vs = get_vectorstore()
        indexed_sources = set(vs.list_sources())
        docs: List[DocumentInfo] = []
        if uploads_dir.exists():
            for f in sorted(uploads_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in _ALLOWED_EXTS:
                    docs.append(DocumentInfo(
                        filename=f.name,
                        size_kb=round(f.stat().st_size / 1024, 1),
                        indexed=f.name in indexed_sources,
                    ))
        return docs

    @app.delete("/documents/{filename}")
    def delete_document(filename: str):
        from fastapi.responses import Response
        safe = _sanitize_filename(filename)
        uploads_dir = settings.resolved_uploads_dir()
        file_path = uploads_dir / safe
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        vs = get_vectorstore()
        vs.delete_by_source(safe)
        file_path.unlink()
        return Response(status_code=204)

    @app.get("/page-preview")
    def page_preview(source: str, page: int) -> Dict[str, Any]:
        vs = get_vectorstore()
        content = vs.get_chunks_by_source_page(source, page)
        return {"source": source, "page": page, "content": content}

    # Catch-all MUST be last — any earlier registration will intercept API routes.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        static_file = _STATIC_DIR / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        index = _STATIC_DIR / "index.html"
        if not index.exists():
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Frontend not built"}, status_code=503)
        return FileResponse(str(index))

    return app


app = create_app()