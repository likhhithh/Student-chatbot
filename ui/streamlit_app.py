from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

# Streamlit runs separately from FastAPI per mandated architecture.
# We keep configuration minimal and environment-driven for Hugging Face Spaces compatibility.


def _api_base_url() -> str:
    """
    Resolve API base URL.

    Why:
    - Locally, FastAPI may run at http://localhost:8000
    - On Hugging Face Spaces, you can set API_BASE_URL in Secrets/Variables.
    """
    return os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _post_json(path: str, payload: Dict[str, Any], timeout: int = 300) -> requests.Response:
    return requests.post(f"{_api_base_url()}{path}", json=payload, timeout=timeout)


def _post_files(path: str, files: List[Any], timeout: int = 600) -> requests.Response:
    return requests.post(f"{_api_base_url()}{path}", files=files, timeout=timeout)


def _health() -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(f"{_api_base_url()}/healthz", timeout=10)
        if r.ok:
            return r.json()
        return None
    except Exception:
        return None


def _ensure_session_id() -> str:
    if "session_id" not in st.session_state or not st.session_state["session_id"]:
        st.session_state["session_id"] = uuid.uuid4().hex
    return st.session_state["session_id"]


def _reset_chat() -> None:
    sid = _ensure_session_id()
    try:
        _post_json("/session/clear", payload={}, timeout=30)  # legacy no-op if misconfigured
    except Exception:
        pass

    # Clear locally regardless; server-side clear is best-effort.
    st.session_state["messages"] = []
    st.session_state["session_id"] = uuid.uuid4().hex


def _init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state["messages"] = []  # list of {"role": "user"/"assistant", "content": str}
    _ensure_session_id()


st.set_page_config(page_title="AI Study Companion", page_icon="📚", layout="centered")
_init_state()

st.title("AI Study Companion")
st.caption("Upload PDFs, then ask questions. Answers come only from your documents.")

with st.sidebar:
    st.header("Setup")
    st.write(f"API: `{_api_base_url()}`")

    health = _health()
    if health:
        st.success(f"Backend OK • vectors: {health.get('vectors', '?')}")
    else:
        st.warning("Backend not reachable. Start FastAPI or set API_BASE_URL.")

    st.divider()

    st.header("Upload PDFs")
    uploaded_files = st.file_uploader(
        "Choose one or more PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        help="PDF text will be extracted, chunked, embedded, and stored in ChromaDB.",
    )

    if st.button("Upload and Index", type="primary", disabled=not uploaded_files):
        with st.spinner("Uploading and indexing..."):
            files_payload = []
            for f in uploaded_files:
                # requests expects tuples: (fieldname, (filename, fileobj, content_type))
                files_payload.append(("files", (f.name, f.getvalue(), "application/pdf")))

            try:
                r = _post_files("/upload", files=files_payload, timeout=900)
            except Exception as e:
                st.error(f"Upload failed: {e}")
            else:
                if r.ok:
                    data = r.json()
                    st.success(
                        f"Indexed {data.get('chunks_indexed', 0)} chunks "
                        f"from {len(data.get('stored_files', []))} file(s)."
                    )
                    st.json(data)
                else:
                    st.error(f"Upload error ({r.status_code}): {r.text}")

    st.divider()
    if st.button("New chat"):
        _reset_chat()
        st.rerun()

# Chat display
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

prompt = st.chat_input("Ask a question about your uploaded documents...")
if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    sid = _ensure_session_id()

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                r = _post_json("/ask", payload={"session_id": sid, "question": prompt}, timeout=300)
            except Exception as e:
                answer_text = f"Error contacting backend: {e}"
                st.error(answer_text)
                st.session_state["messages"].append({"role": "assistant", "content": answer_text})
            else:
                if not r.ok:
                    answer_text = f"API error ({r.status_code}): {r.text}"
                    st.error(answer_text)
                    st.session_state["messages"].append({"role": "assistant", "content": answer_text})
                else:
                    data = r.json()
                    answer = data.get("answer", "")
                    sources = data.get("sources", []) or []

                    st.write(answer)

                    # Sources are optional; show them only if present.
                    if sources:
                        with st.expander("Sources"):
                            for s in sources:
                                st.write(f"- {s}")

                    st.session_state["messages"].append({"role": "assistant", "content": answer})
                    # Persist server-provided session_id (if backend ever changes it).
                    st.session_state["session_id"] = data.get("session_id", sid)