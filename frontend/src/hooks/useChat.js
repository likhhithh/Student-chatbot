import { useState, useCallback, useRef } from 'react'

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

function load(key, def) {
  try { return JSON.parse(localStorage.getItem(key)) || def } catch { return def }
}

function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

export function useChat(showToast) {
  const [messages, setMessages] = useState([])
  const [chats, setChats] = useState(() => load('sb_chats', []))
  const [docs, setDocs] = useState(() => load('sb_docs', []))
  const [chatId, setChatId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)

  const sessionRef = useRef(uid())

  const startNewChat = useCallback(() => {
    const newSid = uid()
    sessionRef.current = newSid
    setChatId(null)
    setMessages([])
    setLoading(false)
    fetch(`/session/clear?session_id=${newSid}`, { method: 'POST' }).catch(() => {})
  }, [])

  const loadChat = useCallback((id) => {
    const chat = chats.find(c => c.id === id)
    if (!chat) return
    setChatId(chat.id)
    sessionRef.current = chat.sid
    setMessages([{
      role: 'assistant',
      text: `Session restored. Continue your conversation about "${chat.title}"`,
      sources: [],
    }])
  }, [chats])

  const uploadFiles = useCallback(async (files) => {
    setUploadProgress({ label: 'Uploading files…', pct: 20 })
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))

    try {
      setUploadProgress({ label: 'Uploading files…', pct: 40 })
      const res = await fetch('/upload', { method: 'POST', body: fd })
      setUploadProgress({ label: 'Indexing chunks…', pct: 80 })

      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: 'Upload failed' }))
        throw new Error(e.detail || 'Upload failed')
      }
      const data = await res.json()
      setUploadProgress({ label: 'Done', pct: 100 })

      setDocs(prev => {
        const next = [...prev]
        files.forEach(f => { if (!next.includes(f.name)) next.push(f.name) })
        save('sb_docs', next)
        return next
      })

      showToast(`✅ Indexed ${data.chunks_indexed} chunks from ${data.stored_files.length} file(s)`, 'ok')
    } finally {
      setTimeout(() => setUploadProgress(null), 600)
    }
  }, [showToast])

  const sendMessage = useCallback(async (question) => {
    const q = question.trim()
    if (!q || loading) return

    let currentChatId = chatId
    if (!currentChatId) {
      currentChatId = uid()
      setChatId(currentChatId)
      setChats(prev => {
        const next = [{ id: currentChatId, title: q.slice(0, 55), sid: sessionRef.current, ts: Date.now() }, ...prev]
        save('sb_chats', next)
        return next
      })
    }

    setMessages(prev => [...prev, { role: 'user', text: q, sources: [] }])
    setLoading(true)

    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionRef.current, question: q }),
      })

      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: 'Server error' }))
        throw new Error(e.detail || `HTTP ${res.status}`)
      }

      const d = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', text: d.answer, sources: d.sources || [] }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', text: `⚠️ ${err.message}`, sources: [] }])
      showToast(err.message, 'err')
    } finally {
      setLoading(false)
    }
  }, [chatId, loading, showToast])

  return {
    messages,
    chats,
    docs,
    chatId,
    loading,
    uploadProgress,
    startNewChat,
    loadChat,
    sendMessage,
    uploadFiles,
  }
}
