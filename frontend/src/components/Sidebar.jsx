import { useState } from 'react'

export default function Sidebar({
  open, chats, chatsLoading, activeChatId,
  memories, user,
  onNewChat, onLoadChat, onToggle, onSignOut,
}) {
  const [showLogoutModal, setShowLogoutModal] = useState(false)

  if (!open) return null

  const avatar = user?.user_metadata?.avatar_url
  const name   = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User'
  const email  = user?.email || ''

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sb-top">
        <div className="logo-wrap">
          <img src="/studygpt-logo.png" alt="StudyGPT" className="sb-logo-img" />
          <span className="logo-name">StudyGPT</span>
        </div>
        <button className="sb-toggle" onClick={onToggle} title="Collapse">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12h18M3 6h18M3 18h18" />
          </svg>
        </button>
      </div>

      {/* New chat */}
      <button className="new-btn" onClick={onNewChat}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New conversation
      </button>

      {/* Chat history */}
      <div className="sb-section-label">Conversations</div>
      <div className="chat-list">
        {chatsLoading ? (
          <div className="sb-loading">
            <div className="sb-skeleton" /><div className="sb-skeleton" /><div className="sb-skeleton" />
          </div>
        ) : chats.length === 0 ? (
          <div className="doc-item" style={{ padding: '8px 4px', fontStyle: 'italic', fontSize: 12 }}>
            No conversations yet
          </div>
        ) : (
          chats.map(c => (
            <div
              key={c.id}
              className={`chat-item ${c.id === activeChatId ? 'active' : ''}`}
              onClick={() => onLoadChat(c.id)}
              title={c.title}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
              </svg>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.title}</span>
            </div>
          ))
        )}
      </div>

      {/* Memory section */}
      {memories.length > 0 && (
        <div className="doc-section">
          <div className="sb-section-label" style={{ padding: '0 0 6px' }}>Recent topics</div>
          {memories.slice(0, 6).map((m, i) => (
            <div key={m.id || i} className="doc-item" title={m.topic}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, opacity: 0.5 }}>
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span style={{ fontSize: 11 }}>{m.topic.length > 28 ? m.topic.slice(0, 28) + '…' : m.topic}</span>
            </div>
          ))}
        </div>
      )}

      {/* User footer */}
      <div className="sb-user">
        <div className="sb-user-info">
          {avatar
            ? <img src={avatar} alt={name} className="sb-avatar" />
            : <div className="sb-avatar sb-avatar-fallback">{name[0].toUpperCase()}</div>
          }
          <div className="sb-user-text">
            <div className="sb-user-name">{name}</div>
            <div className="sb-user-email">{email}</div>
          </div>
        </div>
        <button className="sb-signout" onClick={() => setShowLogoutModal(true)} title="Sign out">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>

      {/* Logout confirmation modal */}
      {showLogoutModal && (
        <div style={modal.overlay} onClick={() => setShowLogoutModal(false)}>
          <div style={modal.box} onClick={e => e.stopPropagation()}>
            <div style={modal.icon}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="2">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </div>
            <h3 style={modal.title}>Sign out?</h3>
            <p style={modal.sub}>You will be returned to the login screen.</p>
            <div style={modal.btns}>
              <button style={modal.cancel} onClick={() => setShowLogoutModal(false)}>Cancel</button>
              <button style={modal.confirm} onClick={() => { setShowLogoutModal(false); onSignOut() }}>Sign out</button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

const modal = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000, backdropFilter: 'blur(2px)',
  },
  box: {
    background: '#fff', borderRadius: 16, padding: '28px 28px 24px',
    width: 320, boxShadow: '0 8px 40px rgba(0,0,0,0.15)',
    border: '1px solid #e5e7eb', textAlign: 'center',
  },
  icon: {
    width: 48, height: 48, borderRadius: '50%', background: '#f3f4f6',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    margin: '0 auto 14px',
  },
  title: { fontSize: 17, fontWeight: 700, color: '#111827', marginBottom: 6 },
  sub: { fontSize: 13, color: '#6b7280', marginBottom: 22, lineHeight: 1.5 },
  btns: { display: 'flex', gap: 10 },
  cancel: {
    flex: 1, padding: '10px', borderRadius: 10, border: '1.5px solid #e5e7eb',
    background: '#fff', color: '#374151', fontSize: 14, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
  },
  confirm: {
    flex: 1, padding: '10px', borderRadius: 10, border: 'none',
    background: '#ef4444', color: '#fff', fontSize: 14, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
  },
}
