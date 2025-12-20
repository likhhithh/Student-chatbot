from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.config import get_settings
from app.prompts.qa_prompt import QA_SYSTEM_INSTRUCTIONS, QA_USER_TEMPLATE
from app.rag.retriever import RetrievedChunk, get_retriever

logger = logging.getLogger(__name__)

IDK = "I don't know"


@dataclass(frozen=True)
class AnswerResult:
    """
    What the API/UI needs.

    We return sources separately to keep the final answer clean while still allowing citations in the UI.
    """
    answer: str
    sources: List[str]


class ChatMemory:
    """
    Lightweight chat memory (per session).

    Why simple list storage:
    - Predictable, easy to serialize later if we add persistence.
    - We only need a bounded window of history to maintain conversational continuity.
    """

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self._turns: List[Tuple[str, str]] = []  # (user, assistant)

    def add_turn(self, user: str, assistant: str) -> None:
        self._turns.append((user, assistant))
        # Keep the most recent turns only (bounded prompts = bounded latency).
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns :]

    def format_for_prompt(self, max_chars: int = 2500) -> str:
        """
        Format history for prompt injection.

        Why max_chars:
        - Limits prompt growth across turns (important on CPU).
        """
        if not self._turns:
            return ""

        blocks: List[str] = []
        used = 0
        # Keep recent turns (from oldest to newest within the retained window).
        for u, a in self._turns:
            b = f"User: {u}\nAssistant: {a}".strip()
            add_len = len(b) + (2 if blocks else 0)
            if used + add_len > max_chars:
                # If history is too large, stop adding older turns.
                break
            blocks.append(b)
            used += add_len

        return "\n\n".join(blocks).strip()


class InMemorySessionStore:
    """
    In-memory session store for chat memory.

    Why:
    - Meets requirement "Maintain chat memory across turns" without external infra.
    - Publicly deployable on Hugging Face Spaces (with the caveat that restarts lose memory).

    Important:
    - This is process-local. For multi-replica deployments, you'd need shared storage (Redis, DB).
    """

    def __init__(self, max_sessions: int = 500) -> None:
        self.max_sessions = max_sessions
        self._store: "OrderedDict[str, ChatMemory]" = OrderedDict()

    def get(self, session_id: str) -> ChatMemory:
        if not session_id:
            # Safe fallback: treat missing session_id as an ephemeral session.
            return ChatMemory()

        mem = self._store.get(session_id)
        if mem is None:
            mem = ChatMemory()
            self._store[session_id] = mem
        else:
            # LRU-ish: mark as recently used to help with eviction.
            self._store.move_to_end(session_id, last=True)

        # Evict oldest sessions if we exceed cap (prevents unbounded RAM usage).
        while len(self._store) > self.max_sessions:
            self._store.popitem(last=False)

        return mem

    def clear(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]


@lru_cache(maxsize=1)
def _load_llm_and_tokenizer():
    """
    Load and cache the HF Transformers model.

    Why cache:
    - Model load dominates startup time on CPU.
    - We want stable latency per request.

    Why seq2seq (FLAN-T5):
    - Generally more reliable for "answer from context" prompting than small causal LMs on CPU.
    """
    settings = get_settings()

    tokenizer = AutoTokenizer.from_pretrained(settings.llm_model_name, use_fast=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(settings.llm_model_name)

    # CPU-only by requirement; keep it explicit for predictability.
    model.to(torch.device(settings.llm_device))
    model.eval()

    return model, tokenizer


class HFSeq2SeqLLM:
    """
    Minimal LLM wrapper around Transformers generate().

    Why not LangChain LLM wrappers:
    - Keeps our usage explicit and reduces surface area (production maintainability).
    - Avoids pulling additional langchain integrations not needed for core RAG.
    """

    def __init__(self) -> None:
        self._model, self._tokenizer = _load_llm_and_tokenizer()
        self._settings = get_settings()

    @torch.inference_mode()
    def generate(self, prompt: str) -> str:
        if not prompt.strip():
            return ""

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            # We don't hardcode max_length; tokenizer/model configs vary.
            # Truncation protects against runaway prompts.
        )
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

        # Determinism matters for "I don't know" compliance; sampling only if temp > 0.
        temperature = float(self._settings.temperature)
        do_sample = temperature > 0.0

        gen = self._model.generate(
            **inputs,
            max_new_tokens=int(self._settings.max_new_tokens),
            do_sample=do_sample,
            temperature=temperature if do_sample else None,
            num_beams=1,  # Keep compute bounded on CPU; beams can increase latency sharply.
        )

        text = self._tokenizer.decode(gen[0], skip_special_tokens=True)
        return (text or "").strip()


def _normalize_answer(text: str) -> str:
    """
    Enforce the required exact "I don't know" output when appropriate.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return IDK

    # If the model expresses uncertainty, standardize to the required string.
    lowered = cleaned.lower().strip()
    if lowered in {"i don't know", "i dont know", "don't know", "dont know"}:
        return IDK
    if lowered.startswith("i don't know") or lowered.startswith("i dont know"):
        return IDK

    return cleaned


def _build_prompt(question: str, context: str, chat_history: str) -> str:
    """
    Build a single text prompt for seq2seq models.

    Why include chat history:
    - Allows follow-up questions ("what about the previous theorem?") to make sense.
    - Still bounded by truncation logic elsewhere.
    """
    parts: List[str] = [QA_SYSTEM_INSTRUCTIONS.strip()]

    if chat_history:
        parts.append("CHAT HISTORY:\n" + chat_history.strip())

    # Context may be empty; in that case the chain will return IDK before calling the model.
    parts.append(QA_USER_TEMPLATE.format(context=context.strip(), question=question.strip()).strip())

    return "\n\n".join(parts).strip()


class RAGChain:
    """
    RAG orchestration:
    - retrieve -> build context -> prompt -> generate -> update memory

    Hard requirement implemented:
    - If answer not found in context, respond "I don't know".
      We enforce this strictly when context is empty, and instruct the model otherwise.
    """

    def __init__(self) -> None:
        self._retriever = get_retriever()
        self._llm = HFSeq2SeqLLM()
        self._sessions = InMemorySessionStore()

    def clear_session(self, session_id: str) -> None:
        self._sessions.clear(session_id)

    def answer(self, session_id: str, question: str) -> AnswerResult:
        q = (question or "").strip()
        if not q:
            return AnswerResult(answer=IDK, sources=[])

        memory = self._sessions.get(session_id)
        chat_history = memory.format_for_prompt(max_chars=2500)

        context, retrieved = self._retriever.build_context(query=q)

        # Strict compliance: if nothing retrieved, we must say "I don't know".
        if not context.strip():
            memory.add_turn(q, IDK)
            return AnswerResult(answer=IDK, sources=[])

        prompt = _build_prompt(question=q, context=context, chat_history=chat_history)
        raw = self._llm.generate(prompt)
        answer = _normalize_answer(raw)

        # If the model didn't follow instructions, the safest behavior is to refuse
        # to hallucinate and return the required fallback.
        if not answer or answer == IDK:
            final = IDK
        else:
            final = answer

        sources = _unique_sources(retrieved)

        memory.add_turn(q, final)
        return AnswerResult(answer=final, sources=sources)


def _unique_sources(chunks: List[RetrievedChunk]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for c in chunks:
        s = (c.citation or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


@lru_cache(maxsize=1)
def get_chain() -> RAGChain:
    """
    Singleton chain for the process.

    Why:
    - Reuses cached LLM + embedding model + vectorstore client.
    - Keeps in-memory chat sessions consistent across API calls.
    """
    return RAGChain()