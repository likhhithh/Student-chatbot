from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars to stay robust on hosted environments.
    )

    # --- App metadata ---
    app_name: str = Field(default="Student Study Chatbot", description="Human-friendly service name")
    environment: Literal["dev", "prod", "test"] = Field(
        default="dev",
        description="Runtime environment, used for behavior toggles and logging.",
    )

    # --- Filesystem paths (kept relative to repo root by default) ---
    # We resolve relative paths against the repository root to avoid surprises when run from different CWDs.
    repo_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[1],
        description="Resolved project root (student-study-chatbot/).",
    )
    uploads_dir: Path = Field(
        default=Path("data/uploads"),
        description="Directory where uploaded PDFs are stored (persistent if supported).",
    )
    chroma_persist_dir: Path = Field(
        default=Path("data/chroma"),
        description="Persistent directory for ChromaDB storage.",
    )

    # --- Chroma / retrieval ---
    chroma_collection: str = Field(
        default="study_docs",
        description="Chroma collection name used to store document embeddings.",
    )
    top_k: int = Field(default=4, ge=1, le=20, description="Number of chunks to retrieve per question.")

    # --- Chunking ---
    chunk_size: int = Field(
        default=1000,
        ge=200,
        le=4000,
        description="Chunk size in characters. Character-based is predictable and fast on CPU.",
    )
    chunk_overlap: int = Field(
        default=150,
        ge=0,
        le=1000,
        description="Overlap improves answer continuity across chunk boundaries.",
    )

    # --- Embeddings ---
    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Fast, high-quality embedding model suitable for CPU usage.",
    )

    # --- LLM (Transformers) ---
    llm_model_name: str = Field(
        default="google/flan-t5-base",
        description=(
            "Instruction-tuned model that runs on CPU reasonably well. "
            "We use seq2seq generation for stable 'answer from context' behavior."
        ),
    )
    llm_device: Literal["cpu"] = Field(
        default="cpu",
        description="CPU-only per project constraints (MacBook Air M1).",
    )
    max_new_tokens: int = Field(
        default=256,
        ge=16,
        le=1024,
        description="Caps response length for predictable latency and cost.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.5,
        description="0.0 encourages deterministic extraction from context (reduces hallucinations).",
    )

    # --- API / CORS ---
    # Streamlit may run on a different origin than FastAPI (especially on Spaces),
    # so we keep a permissive default and allow tightening via env vars.
    cors_allow_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed origins for CORS; '*' for simplest deploys.",
    )

    def resolved_uploads_dir(self) -> Path:
        """Resolve uploads directory relative to repo root unless it's absolute."""
        p = self.uploads_dir
        return p if p.is_absolute() else (self.repo_root / p).resolve()

    def resolved_chroma_persist_dir(self) -> Path:
        """Resolve Chroma persist directory relative to repo root unless it's absolute."""
        p = self.chroma_persist_dir
        return p if p.is_absolute() else (self.repo_root / p).resolve()

    def ensure_dirs(self) -> None:
        """
        Create required directories at startup.

        Why here:
        - Centralizes filesystem expectations.
        - Avoids racey "create if needed" sprinkled across modules.
        """
        self.resolved_uploads_dir().mkdir(parents=True, exist_ok=True)
        self.resolved_chroma_persist_dir().mkdir(parents=True, exist_ok=True)

    def cors_origins_list(self) -> list[str]:
        """
        Parse CORS origins into a list.

        Supports:
        - '*' (single wildcard)
        - comma-separated origins
        """
        raw = (self.cors_allow_origins or "").strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
