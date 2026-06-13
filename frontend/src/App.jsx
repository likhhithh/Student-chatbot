import { useState, useCallback, useEffect } from 'react'
import { supabase } from './lib/supabase'
import Auth from './components/Auth'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputZone from './components/InputZone'
import ToastContainer from './components/ToastContainer'
import Analytics from './components/Analytics'
import Documents from './components/Documents'
import { useChat } from './hooks/useChat'
import { useToast } from './hooks/useToast'
import { useMemory } from './hooks/useMemory'
import './App.css'

export default function App() {
  const [session, setSession]         = useState(undefined)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [pendingPrompt, setPendingPrompt] = useState('')
  const [view, setView] = useState('chat') // 'chat' | 'analytics' | 'documents'
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')
  const { toasts, showToast }         = useToast()

  // Auth listener
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const userId = session?.user?.id

  // Memory hook — per user
  const { memories, saveTopic, buildContextString } = useMemory(userId)

  // Chat hook — persists to Supabase
  const {
    messages, chats, chatId, loading, chatsLoading,
    loadChatList, startNewChat, loadChat, sendMessage, uploadFiles, submitFeedback,
  } = useChat(userId, showToast, buildContextString, saveTopic)

  // Load chat list when user is known
  useEffect(() => {
    if (userId) loadChatList()
  }, [userId, loadChatList])

  const handleSend = useCallback(async (question, files) => {
    if (files.length > 0) await uploadFiles(files)
    if (question.trim()) await sendMessage(question)
  }, [uploadFiles, sendMessage])

  async function handleSignOut() {
    await supabase.auth.signOut()
  }

  function exportChat() {
    if (!messages.length) return
    const title = chatId ? (chats.find(c => c.id === chatId)?.title || 'chat') : 'chat'
    const md = messages.map(m =>
      `**${m.role === 'user' ? 'You' : 'StudyGPT'}:**\n\n${m.text}`
    ).join('\n\n---\n\n')
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title.replace(/[^a-z0-9]/gi, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Loading splash
  if (session === undefined) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: '#fff' }}>
        <img src="/studygpt-logo.png" alt="StudyGPT" style={{ height: 36, opacity: 0.5 }} />
      </div>
    )
  }

  if (!session) return <Auth />

  const user = session.user
  const chatTitle = chatId
    ? (chats.find(c => c.id === chatId)?.title || 'Chat')
    : 'New conversation'

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        chats={chats}
        chatsLoading={chatsLoading}
        activeChatId={chatId}
        activeView={view}
        memories={memories}
        user={user}
        dark={dark}
        onNewChat={startNewChat}
        onLoadChat={loadChat}
        onToggle={() => setSidebarOpen(o => !o)}
        onSignOut={handleSignOut}
        onViewChange={setView}
        onDarkToggle={() => setDark(d => !d)}
      />
      <div className="main">
        {view === 'analytics' ? (
          <Analytics userId={userId} onBack={() => setView('chat')} />
        ) : view === 'documents' ? (
          <Documents onBack={() => setView('chat')} />
        ) : (
          <>
            <div className="topbar">
              {!sidebarOpen && (
                <button className="sb-toggle" onClick={() => setSidebarOpen(true)} title="Open sidebar">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 12h18M3 6h18M3 18h18" />
                  </svg>
                </button>
              )}
              <span className="topbar-title">{chatTitle}</span>
              {messages.length > 0 && (
                <button className="export-btn" onClick={exportChat} title="Export chat">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Export
                </button>
              )}
            </div>
            <ChatArea messages={messages} loading={loading} onPromptSelect={setPendingPrompt} onFeedback={submitFeedback} onFollowup={sendMessage} />
            <InputZone
              onSend={handleSend}
              loading={loading}
              pendingPrompt={pendingPrompt}
              onPromptConsumed={() => setPendingPrompt('')}
            />
          </>
        )}
      </div>
      <ToastContainer toasts={toasts} />
    </div>
  )
}
