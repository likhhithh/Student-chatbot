from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterator, Optional

import boto3

logger = logging.getLogger(__name__)


class BedrockLLM:
    """
    Bedrock Converse API wrapper — works for Claude, OpenAI on Bedrock, Llama, Titan, etc.
    """

    def __init__(
        self,
        model_id: str,
        region: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        kwargs: dict = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            kwargs["aws_access_key_id"] = aws_access_key_id
            kwargs["aws_secret_access_key"] = aws_secret_access_key

        self._client = boto3.client("bedrock-runtime", **kwargs)
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._temperature = temperature

    def generate(self, prompt: str) -> str:
        if not prompt.strip():
            return ""

        response = self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={
                "maxTokens": self._max_tokens,
                "temperature": self._temperature,
            },
        )

        logger.debug("Bedrock raw response: %s", response)

        # Extract text robustly — different models use different content block shapes
        try:
            content_blocks = response["output"]["message"]["content"]
            parts = []
            for block in content_blocks:
                if "text" in block:
                    parts.append(block["text"])
                elif "content" in block:
                    # Some models nest content one level deeper
                    inner = block["content"]
                    if isinstance(inner, str):
                        parts.append(inner)
                    elif isinstance(inner, list):
                        for ib in inner:
                            if isinstance(ib, dict) and "text" in ib:
                                parts.append(ib["text"])
            if parts:
                return " ".join(parts).strip()
        except (KeyError, IndexError, TypeError):
            pass

        # Last-resort: log the shape so we can fix it
        logger.error("Unexpected Bedrock response shape: %s", response)
        return ""

    def generate_stream(self, prompt: str) -> Iterator[str]:
        if not prompt.strip():
            return
        response = self._client.converse_stream(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": self._temperature},
        )
        for event in response.get("stream", []):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    yield delta["text"]


@lru_cache(maxsize=1)
def get_bedrock_llm() -> BedrockLLM:
    from app.config import get_settings
    s = get_settings()
    return BedrockLLM(
        model_id=s.bedrock_chat_model_id,
        region=s.aws_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        max_tokens=s.max_new_tokens,
        temperature=s.temperature,
    )
