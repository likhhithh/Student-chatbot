from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import boto3

logger = logging.getLogger(__name__)


class BedrockLLM:
    """
    Bedrock Converse API wrapper — works for any model that supports the Converse API
    (Anthropic Claude, Amazon Titan, OpenAI on Bedrock, Meta Llama, etc.).
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
        if aws_access_key_id:
            kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
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
        return response["output"]["message"]["content"][0]["text"].strip()


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
