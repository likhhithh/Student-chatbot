import { useState, useCallback, useRef } from 'react'
import { supabase } from '../lib/supabase'

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export function useChat(userId, showToast, buildMemoryContext, saveTopic) {
  const [messages, setMessages]   = useState([])
  const [chats, setChats]         = useState([])
  const [chatId, setChatId]       = useState(null)   // Supabase chat row id
  const [loading, setLoading]     = useState(false)
  const [chatsLoading, setChatsLoading] = useState(true)

  const sessionRef = useRef(uid())
  const chatIdRef  = useRef(null) // keep in sync with chatId for callbacks

  // ── Load chat list on mount ──────────────────────────────────────────────
  const loadChatList = useCallback(async () => {
    if (!userId) return
    setChatsLoading(true)
    const { data } = await supabase
      .from('chats')
      .select('id, title, session_id, created_at')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(50)
    if (data) setChats(data)
    setChatsLoading(false)
  }, [userId])

  // ── Start new chat ───────────────────────────────────────────────────────
  const startNewChat = useCallback(() => {
    const newSid = uid()
    sessionRef.current = newSid
    chatIdRef.current  = null
    setChatId(null)
    setMessages([])
    setLoading(false)
    fetch(`/session/clear?session_id=${newSid}`, { method: 'POST' }).catch(() => {})
  }, [])

  // ── Load an existing chat ────────────────────────────────────────────────
  const loadChat = useCallback(async (id) => {
    const chat = chats.find(c => c.id === id)
    if (!chat) return

    setChatId(chat.id)
    chatIdRef.current = chat.id
    sessionRef.current = chat.session_id

    // Fetch messages from Supabase
    const { data: msgs } = await supabase
      .from('messages')
      .select('id, role, content, sources, feedback')
      .eq('chat_id', chat.id)
      .order('created_at', { ascending: true })

    if (msgs) {
      setMessages(msgs.map(m => ({
        id: m.id,
        role: m.role,
        text: m.content,
        sources: m.sources || [],
        feedback: m.feedback ?? null,
      })))

      // Restore backend session memory
      if (msgs.length > 0) {
        fetch('/session/restore', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: chat.session_id,
            messages: msgs.map(m => ({ role: m.role, content: m.content })),
          }),
        }).catch(() => {})
      }
    }
  }, [chats])

  // ── Upload files ─────────────────────────────────────────────────────────
  const uploadFiles = useCallback(async (files) => {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    fd.append('session_id', sessionRef.current)

    const res = await fetch('/upload', { method: 'POST', body: fd })
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(e.detail || 'Upload failed')
    }
    const data = await res.json()
    showToast(`Indexed ${data.chunks_indexed} chunks from ${data.stored_files.length} file(s)`, 'ok')
  }, [showToast])

  // ── Send message (streaming) ─────────────────────────────────────────────
  const sendMessage = useCallback(async (question) => {
    const q = question.trim()
    if (!q || loading) return

    let currentChatId = chatIdRef.current
    if (!currentChatId) {
      const { data: newChat } = await supabase
        .from('chats')
        .insert({ user_id: userId, title: q.slice(0, 60), session_id: sessionRef.current })
        .select()
        .single()
      if (newChat) {
        currentChatId = newChat.id
        chatIdRef.current = newChat.id
        setChatId(newChat.id)
        setChats(prev => [newChat, ...prev])
      }
    }

    setMessages(prev => [...prev, { role: 'user', text: q, sources: [] }])
    setLoading(true)

    if (currentChatId) {
      supabase.from('messages').insert({ chat_id: currentChatId, role: 'user', content: q, sources: [] }).then(() => {})
    }

    saveTopic?.(q)

    // Add empty assistant placeholder — tokens stream into it
    setMessages(prev => [...prev, { id: null, role: 'assistant', text: '', sources: [], feedback: null }])

    try {
      const res = await fetch('/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id:   sessionRef.current,
          question:     q,
          user_context: buildMemoryContext?.() || null,
        }),
      })

      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: 'Server error' }))
        throw new Error(e.detail || `HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let fullText = ''
      let sources = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = JSON.parse(line.slice(6))
          if (data.error) throw new Error(data.error)
          if (data.token) {
            fullText += data.token
            setMessages(prev => {
              const next = [...prev]
              next[next.length - 1] = { ...next[next.length - 1], text: fullText }
              return next
            })
          }
          if (data.done) {
            sources = data.sources || []
            const conf = data.confidence || 'medium'
            const followups = data.followups || []
            setMessages(prev => {
              const next = [...prev]
              next[next.length - 1] = { ...next[next.length - 1], sources, confidence: conf, followups }
              return next
            })
          }
        }
      }

      // Save completed assistant message and capture ID for feedback
      if (currentChatId && fullText) {
        const { data: savedMsg } = await supabase.from('messages').insert({
          chat_id: currentChatId, role: 'assistant', content: fullText, sources,
        }).select('id').single()
        const msgId = savedMsg?.id ?? null
        if (msgId) {
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = { ...next[next.length - 1], id: msgId }
            return next
          })
        }
      }

      if (currentChatId) {
        supabase.from('chats').update({ updated_at: new Date().toISOString() }).eq('id', currentChatId).then(() => {})
      }

    } catch (err) {
      setMessages(prev => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', text: `Error: ${err.message}`, sources: [] }
        return next
      })
      showToast(err.message, 'err')
    } finally {
      setLoading(false)
    }
  }, [loading, userId, showToast, buildMemoryContext, saveTopic])

  const submitFeedback = useCallback(async (messageId, rating) => {
    if (!messageId) return
    await supabase.from('messages').update({ feedback: rating }).eq('id', messageId)
    setMessages(prev => prev.map(m => m.id === messageId ? { ...m, feedback: rating } : m))
  }, [])

  return {
    messages,
    chats,
    chatId,
    loading,
    chatsLoading,
    loadChatList,
    startNewChat,
    loadChat,
    sendMessage,
    uploadFiles,
    submitFeedback,
  }
}
