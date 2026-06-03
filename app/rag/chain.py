from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple

from app.prompts.qa_prompt import QA_SYSTEM_INSTRUCTIONS, QA_USER_TEMPLATE
from app.rag.bedrock_llm import get_bedrock_llm
from app.rag.retriever import RetrievedChunk, get_retriever

logger = logging.getLogger(__name__)

IDK = "I don't know"


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: List[str]


class ChatMemory:
    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self._turns: List[Tuple[str, str]] = []

    def add_turn(self, user: str, assistant: str) -> None:
        self._turns.append((user, assistant))
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def format_for_prompt(self, max_chars: int = 2500) -> str:
        if not self._turns:
            return ""
        blocks: List[str] = []
        used = 0
        for u, a in self._turns:
            b = f"User: {u}\nAssistant: {a}".strip()
            add_len = len(b) + (2 if blocks else 0)
            if used + add_len > max_chars:
                break
            blocks.append(b)
            used += add_len
        return "\n\n".join(blocks).strip()


class InMemorySessionStore:
    def __init__(self, max_sessions: int = 500) -> None:
        self.max_sessions = max_sessions
        self._store: "OrderedDict[str, ChatMemory]" = OrderedDict()

    def get(self, session_id: str) -> ChatMemory:
        if not session_id:
            return ChatMemory()
        mem = self._store.get(session_id)
        if mem is None:
            mem = ChatMemory()
            self._store[session_id] = mem
        else:
            self._store.move_to_end(session_id, last=True)
        while len(self._store) > self.max_sessions:
            self._store.popitem(last=False)
        return mem

    def clear(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]


def _normalize_answer(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return IDK
    lowered = cleaned.lower().strip()
    if lowered in {"i don't know", "i dont know", "don't know", "dont know"}:
        return IDK
    if lowered.startswith("i don't know") or lowered.startswith("i dont know"):
        return IDK
    return cleaned


def _build_prompt(question: str, context: str, chat_history: str) -> str:
    parts: List[str] = [QA_SYSTEM_INSTRUCTIONS.strip()]
    if chat_history:
        parts.append("CHAT HISTORY:\n" + chat_history.strip())
    parts.append(QA_USER_TEMPLATE.format(context=context.strip(), question=question.strip()).strip())
    return "\n\n".join(parts).strip()


class RAGChain:
    def __init__(self) -> None:
        self._retriever = get_retriever()
        self._llm = get_bedrock_llm()
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

        if not context.strip():
            memory.add_turn(q, IDK)
            return AnswerResult(answer=IDK, sources=[])

        prompt = _build_prompt(question=q, context=context, chat_history=chat_history)
        raw = self._llm.generate(prompt)
        answer = _normalize_answer(raw)

        final = IDK if not answer or answer == IDK else answer
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
    return RAGChain()
