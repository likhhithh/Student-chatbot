from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List

# Important macOS stability defaults:
# - TOKENIZERS_PARALLELISM=false prevents HF tokenizers from using a global threadpool
#   that can interact badly with forked processes.
# - Forcing SentenceTransformer to CPU prevents PyTorch MPS initialization, which is a
#   common cause of hard crashes ("bus error") when any forking occurs later.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


from sentence_transformers import SentenceTransformer


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    device: str = "cpu"  # Strict CPU-only per project constraints and macOS stability.


@lru_cache(maxsize=1)
def _load_embedding_model(model_name: str, device: str) -> SentenceTransformer:
    """
    Load and cache the embedding model.

    Why:
    - Model load is expensive on CPU.
    - Caching avoids reload across requests and modules.

    Critical decision:
    - Force device="cpu" to avoid MPS on macOS (prevents intermittent bus errors).
    """
    return SentenceTransformer(model_name, device=device)


class SentenceTransformerEmbeddings:
    """
    Minimal embeddings wrapper.

    Why custom wrapper:
    - Keeps behavior explicit and stable across langchain package changes.
    - Chroma accepts raw vectors, so we don't need heavier abstractions.
    """

    def __init__(self, config: EmbeddingConfig):
        self._config = config
        self._model = _load_embedding_model(config.model_name, config.device)

    @property
    def dimension(self) -> int:
        # Infer dimension without relying on internal attributes.
        vec = self.embed_query("dimension probe")
        return len(vec)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts.

        Why normalize_embeddings:
        - Improves stability for cosine similarity retrieval.
        """
        if not texts:
            return []

        vectors = self._model.encode(
            texts,
            batch_size=32,  # Balanced for CPU-only on M1.
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> List[float]:
        if not text:
            return []

        vector = self._model.encode(
            [text],
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
        )[0]
        return vector.tolist()