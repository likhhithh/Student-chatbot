export default function Sidebar({ open, chats, activeChatId, user, onNewChat, onLoadChat, onToggle, onSignOut }) {
  if (!open) return null

  const avatar = user?.user_metadata?.avatar_url
  const name   = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User'
  const email  = user?.email || ''

  return (
    <aside className="sidebar">
      {/* Top — logo */}
      <div className="sb-top">
        <div className="logo-wrap">
          <img src="/studygpt-logo.png" alt="StudyGPT" className="sb-logo-img" />
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
      <div className="sb-section-label">Recent chats</div>
      <div className="chat-list">
        {chats.length === 0
          ? <div className="doc-item" style={{ padding: '8px 4px', fontStyle: 'italic', fontSize: 12 }}>No chats yet</div>
          : chats.slice(0, 40).map(c => (
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
        }
      </div>

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
        <button className="sb-signout" onClick={onSignOut} title="Sign out">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>
    </aside>
  )
}
