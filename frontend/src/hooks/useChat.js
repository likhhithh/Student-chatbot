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
      .select('role, content, sources')
      .eq('chat_id', chat.id)
      .order('created_at', { ascending: true })

    if (msgs) {
      setMessages(msgs.map(m => ({
        role: m.role,
        text: m.content,
        sources: m.sources || [],
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

    const res = await fetch('/upload', { method: 'POST', body: fd })
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(e.detail || 'Upload failed')
    }
    const data = await res.json()
    showToast(`Indexed ${data.chunks_indexed} chunks from ${data.stored_files.length} file(s)`, 'ok')
  }, [showToast])

  // ── Send message ─────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (question) => {
    const q = question.trim()
    if (!q || loading) return

    // ── Create chat row in Supabase if first message ─────────────────────
    let currentChatId = chatIdRef.current
    if (!currentChatId) {
      const { data: newChat } = await supabase
        .from('chats')
        .insert({
          user_id:    userId,
          title:      q.slice(0, 60),
          session_id: sessionRef.current,
        })
        .select()
        .single()

      if (newChat) {
        currentChatId = newChat.id
        chatIdRef.current = newChat.id
        setChatId(newChat.id)
        setChats(prev => [newChat, ...prev])
      }
    }

    // ── Optimistic user message ──────────────────────────────────────────
    setMessages(prev => [...prev, { role: 'user', text: q, sources: [] }])
    setLoading(true)

    // Save user message to Supabase
    if (currentChatId) {
      supabase.from('messages').insert({
        chat_id: currentChatId,
        role: 'user',
        content: q,
        sources: [],
      }).then(() => {})
    }

    // Save topic to memory (the question itself is the topic signal)
    saveTopic?.(q)

    try {
      const res = await fetch('/ask', {
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

      const d = await res.json()
      const assistantMsg = { role: 'assistant', text: d.answer, sources: d.sources || [] }
      setMessages(prev => [...prev, assistantMsg])

      // Save assistant message to Supabase
      if (currentChatId) {
        supabase.from('messages').insert({
          chat_id: currentChatId,
          role: 'assistant',
          content: d.answer,
          sources: d.sources || [],
        }).then(() => {})
      }

      // Update chat's updated_at
      if (currentChatId) {
        supabase.from('chats').update({ updated_at: new Date().toISOString() })
          .eq('id', currentChatId).then(() => {})
      }

    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', text: `Error: ${err.message}`, sources: [] }])
      showToast(err.message, 'err')
    } finally {
      setLoading(false)
    }
  }, [loading, userId, showToast, buildMemoryContext, saveTopic])

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
  }
}
