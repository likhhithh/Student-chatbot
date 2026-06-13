from __future__ import annotations

import logging
from collections import OrderedDict
import json as _json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from app.prompts.qa_prompt import QA_SYSTEM_INSTRUCTIONS, QA_USER_TEMPLATE
from app.rag.bedrock_llm import get_bedrock_llm
from app.rag.retriever import RetrievedChunk, get_retriever

logger = logging.getLogger(__name__)

IDK = "I don't know"


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: List[str]
    confidence: str = "medium"
    followups: List[str] = field(default_factory=list)


class ChatMemory:
    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self._turns: List[Tuple[str, str]] = []

    def add_turn(self, user: str, assistant: str) -> None:
        self._turns.append((user, assistant))
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def restore(self, messages: List[Dict[str, str]]) -> None:
        """Restore past messages into memory (pairs of user/assistant turns)."""
        self._turns.clear()
        user_msg = None
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "").strip()
            if role == "user":
                user_msg = content
            elif role == "assistant" and user_msg:
                self._turns.append((user_msg, content))
                user_msg = None
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def format_for_prompt(self, max_chars: int = 3000) -> str:
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


def _calc_confidence(chunks: List[RetrievedChunk]) -> str:
    if not chunks:
        return "low"
    best_dist = min(c.distance for c in chunks)
    if best_dist < 0.25:
        return "high"
    if best_dist < 0.50:
        return "medium"
    return "low"


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


def _build_prompt(
    question: str,
    context: str,
    chat_history: str,
    user_context: Optional[str] = None,
) -> str:
    parts: List[str] = [QA_SYSTEM_INSTRUCTIONS.strip()]

    if user_context:
        parts.append("USER MEMORY (topics this student has previously studied):\n" + user_context.strip())

    if chat_history:
        parts.append("CHAT HISTORY:\n" + chat_history.strip())

    parts.append(QA_USER_TEMPLATE.format(context=context.strip(), question=question.strip()).strip())
    return "\n\n".join(parts).strip()


def _generate_followups(llm: Any, question: str, answer: str) -> List[str]:
    prompt = (
        "Based on this Q&A, generate exactly 3 short follow-up questions a student might ask next.\n"
        "Return ONLY a JSON array of 3 strings. No explanation, no markdown, no extra text.\n\n"
        f"Question: {question}\n"
        f"Answer: {answer[:600]}\n\n"
        "JSON array:"
    )
    try:
        raw = llm.generate(prompt).strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            items = _json.loads(raw[start:end])
            if isinstance(items, list):
                return [str(q).strip() for q in items[:3] if q]
    except Exception:
        pass
    return []


class RAGChain:
    def __init__(self) -> None:
        self._retriever = get_retriever()
        self._llm = get_bedrock_llm()
        self._sessions = InMemorySessionStore()

    def clear_session(self, session_id: str) -> None:
        self._sessions.clear(session_id)

    def restore_session(self, session_id: str, messages: List[Dict[str, str]]) -> None:
        mem = self._sessions.get(session_id)
        mem.restore(messages)

    def answer(
        self,
        session_id: str,
        question: str,
        user_context: Optional[str] = None,
    ) -> AnswerResult:
        q = (question or "").strip()
        if not q:
            return AnswerResult(answer=IDK, sources=[])

        memory = self._sessions.get(session_id)
        chat_history = memory.format_for_prompt(max_chars=3000)

        where = {"session_id": session_id} if session_id else None
        context, retrieved = self._retriever.build_context(query=q, where=where)

        if not context.strip():
            memory.add_turn(q, IDK)
            return AnswerResult(answer=IDK, sources=[])

        prompt = _build_prompt(
            question=q,
            context=context,
            chat_history=chat_history,
            user_context=user_context,
        )
        raw = self._llm.generate(prompt)
        answer = _normalize_answer(raw)

        final = IDK if not answer or answer == IDK else answer
        sources = _unique_sources(retrieved)

        memory.add_turn(q, final)
        return AnswerResult(answer=final, sources=sources, confidence=_calc_confidence(retrieved))


    def answer_stream(
        self,
        session_id: str,
        question: str,
        user_context: Optional[str] = None,
    ) -> Generator[Union[str, AnswerResult], None, None]:
        q = (question or "").strip()
        if not q:
            yield IDK
            yield AnswerResult(answer=IDK, sources=[], confidence="low")
            return

        memory = self._sessions.get(session_id)
        chat_history = memory.format_for_prompt(max_chars=3000)
        where = {"session_id": session_id} if session_id else None
        context, retrieved = self._retriever.build_context(query=q, where=where)

        if not context.strip():
            memory.add_turn(q, IDK)
            yield IDK
            yield AnswerResult(answer=IDK, sources=[], confidence="low")
            return

        prompt = _build_prompt(
            question=q,
            context=context,
            chat_history=chat_history,
            user_context=user_context,
        )

        parts: List[str] = []
        first = True
        for token in self._llm.generate_stream(prompt):
            if first:
                token = token.lstrip('| \n')
                first = False
                if not token:
                    continue
            parts.append(token)
            yield token

        answer = _normalize_answer("".join(parts))
        final = IDK if not answer or answer == IDK else answer
        sources = _unique_sources(retrieved)
        memory.add_turn(q, final)
        followups = _generate_followups(self._llm, q, final) if final != IDK else []
        yield AnswerResult(answer=final, sources=sources, confidence=_calc_confidence(retrieved), followups=followups)


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
