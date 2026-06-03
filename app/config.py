from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

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
        default="study_docs_bedrock",
        description="Chroma collection name used to store document embeddings.",
    )
    top_k: int = Field(default=4, ge=1, le=20, description="Number of chunks to retrieve per question.")

    # --- Chunking ---
    chunk_size: int = Field(
        default=1000,
        ge=200,
        le=4000,
        description="Chunk size in characters.",
    )
    chunk_overlap: int = Field(
        default=150,
        ge=0,
        le=1000,
        description="Overlap improves answer continuity across chunk boundaries.",
    )

    # --- AWS Bedrock credentials ---
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS IAM access key ID.")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS IAM secret access key.")
    aws_region: str = Field(default="ap-south-1", description="AWS region for Bedrock.")

    # --- Bedrock model IDs ---
    bedrock_chat_model_id: str = Field(
        default="openai.gpt-oss-120b-1:0",
        description="Bedrock model ID for the chat/LLM. Must be enabled in your Bedrock console.",
    )
    bedrock_embedding_model_id: str = Field(
        default="amazon.titan-embed-text-v2:0",
        description="Bedrock model ID for embeddings (Amazon Titan Text V2, 1024-dim).",
    )

    # --- Generation settings ---
    max_new_tokens: int = Field(
        default=512,
        ge=16,
        le=4096,
        description="Max tokens for LLM response.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.5,
        description="0.0 encourages deterministic extraction from context.",
    )

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
