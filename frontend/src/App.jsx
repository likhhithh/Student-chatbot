import { useState, useCallback, useEffect } from 'react'
import { supabase } from './lib/supabase'
import Auth from './components/Auth'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputZone from './components/InputZone'
import ToastContainer from './components/ToastContainer'
import { useChat } from './hooks/useChat'
import { useToast } from './hooks/useToast'
import './App.css'

export default function App() {
  const [session, setSession]       = useState(undefined) // undefined = loading
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [pendingPrompt, setPendingPrompt] = useState('')
  const { toasts, showToast }       = useToast()

  const {
    messages, chats, chatId, loading,
    startNewChat, loadChat, sendMessage, uploadFiles,
  } = useChat(showToast)

  // Auth listener
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  const handleSend = useCallback(async (question, files) => {
    if (files.length > 0) await uploadFiles(files)
    if (question.trim()) await sendMessage(question)
  }, [uploadFiles, sendMessage])

  async function handleSignOut() {
    await supabase.auth.signOut()
  }

  // Loading splash
  if (session === undefined) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: '#fff' }}>
        <img src="/studygpt-logo.png" alt="StudyGPT" style={{ height: 36, opacity: 0.6 }} />
      </div>
    )
  }

  // Not logged in → auth screen
  if (!session) return <Auth />

  // Logged in → main app
  const user = session.user
  const chatTitle = chatId ? (chats.find(c => c.id === chatId)?.title || 'Chat') : 'New conversation'

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        chats={chats}
        activeChatId={chatId}
        user={user}
        onNewChat={startNewChat}
        onLoadChat={loadChat}
        onToggle={() => setSidebarOpen(o => !o)}
        onSignOut={handleSignOut}
      />
      <div className="main">
        <div className="topbar">
          {!sidebarOpen && (
            <button className="sb-toggle" onClick={() => setSidebarOpen(true)} title="Open sidebar">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12h18M3 6h18M3 18h18" />
              </svg>
            </button>
          )}
          <span className="topbar-title">{chatTitle}</span>
        </div>
        <ChatArea messages={messages} loading={loading} onPromptSelect={setPendingPrompt} />
        <InputZone
          onSend={handleSend}
          loading={loading}
          pendingPrompt={pendingPrompt}
          onPromptConsumed={() => setPendingPrompt('')}
        />
      </div>
      <ToastContainer toasts={toasts} />
    </div>
  )
}
