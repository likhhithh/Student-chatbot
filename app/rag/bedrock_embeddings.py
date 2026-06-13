from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import List, Optional

import boto3

logger = logging.getLogger(__name__)


class BedrockTitanEmbeddings:
    """
    Amazon Titan Text V2 embeddings via AWS Bedrock.

    Produces 1024-dimensional normalized embeddings.
    Uses boto3 invoke_model — no external SDK dependency beyond boto3.
    """

    def __init__(
        self,
        model_id: str,
        region: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ) -> None:
        kwargs: dict = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            kwargs["aws_access_key_id"] = aws_access_key_id
            kwargs["aws_secret_access_key"] = aws_secret_access_key

        self._client = boto3.client("bedrock-runtime", **kwargs)
        self._model_id = model_id

    def embed_query(self, text: str) -> List[float]:
        if not text:
            return []
        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["embedding"]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(t) for t in texts]


@lru_cache(maxsize=1)
def get_bedrock_embedder() -> BedrockTitanEmbeddings:
    from app.config import get_settings
    s = get_settings()
    return BedrockTitanEmbeddings(
        model_id=s.bedrock_embedding_model_id,
        region=s.aws_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
    )
