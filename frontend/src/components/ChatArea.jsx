import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const PROMPT_CARDS = [
  { title: 'Summarize key concepts', sub: 'From my uploaded notes', text: 'Summarize the key concepts from my notes' },
  { title: 'Explain in simple terms', sub: 'Any topic from the material', text: 'Explain this topic in simple terms' },
  { title: 'Important formulas', sub: 'To remember for the exam', text: 'What are the important formulas I should remember for the exam?' },
  { title: 'Quiz me', sub: 'Test my understanding with 5 questions', text: 'Quiz me on this chapter with 5 questions' },
]

export default function ChatArea({ messages, loading, onPromptSelect, onFeedback, onFollowup }) {
  const bottomRef = useRef(null)
  const [preview, setPreview] = useState(null) // { source, page, content } | null
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSourceClick(citation) {
    const match = citation.match(/^(.+) \(page (\d+)\)$/)
    if (!match) return
    const [, source, page] = match
    setPreviewLoading(true)
    setPreview({ source, page: parseInt(page), content: null })
    try {
      const res = await fetch(`/page-preview?source=${encodeURIComponent(source)}&page=${page}`)
      const data = await res.json()
      setPreview({ source, page: parseInt(page), content: data.content || 'No content found for this page.' })
    } catch {
      setPreview({ source, page: parseInt(page), content: 'Failed to load page content.' })
    } finally {
      setPreviewLoading(false)
    }
  }

  const showWelcome = messages.length === 0 && !loading

  return (
    <>
      <div className="chat-scroll">
        <div className="chat-wrap">
          {showWelcome && (
            <div className="welcome">
              <h1 className="wlc-h">Welcome to StudyGPT</h1>
              <p className="wlc-sub">
                Upload your PDFs or photos of notes, then ask anything.
                I'll answer strictly from your documents — powered by AWS Bedrock.
              </p>
              <div className="prompts">
                {PROMPT_CARDS.map((card, i) => (
                  <div key={i} className="prompt-card" onClick={() => onPromptSelect?.(card.text)}>
                    <div className="pt">{card.title}</div>
                    <div className="ps">{card.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <Message
              key={i}
              {...msg}
              isStreaming={loading && i === messages.length - 1 && msg.role === 'assistant'}
              onFeedback={onFeedback}
              onFollowup={onFollowup}
              onSourceClick={handleSourceClick}
            />
          ))}

          {loading && messages[messages.length - 1]?.role !== 'assistant' && (
            <div className="msg assistant">
              <div className="msg-av">S</div>
              <div className="msg-body">
                <div className="msg-name">StudyGPT</div>
                <div className="dots">
                  <div className="dot" /><div className="dot" /><div className="dot" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Page preview modal */}
      {preview && (
        <div className="preview-overlay" onClick={() => setPreview(null)}>
          <div className="preview-modal" onClick={e => e.stopPropagation()}>
            <div className="preview-header">
              <div className="preview-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span>{preview.source}</span>
                <span className="preview-page-badge">Page {preview.page}</span>
              </div>
              <button className="preview-close" onClick={() => setPreview(null)}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div className="preview-body">
              {previewLoading
                ? <div className="preview-loading">Loading page content…</div>
                : <pre className="preview-text">{preview.content}</pre>
              }
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function Message({ id, role, text, sources, feedback, confidence, followups, isStreaming, onFeedback, onFollowup, onSourceClick }) {
  const [voted, setVoted] = useState(feedback ?? null)
  const [copied, setCopied] = useState(false)

  function handleVote(rating) {
    const next = voted === rating ? null : rating
    setVoted(next)
    onFeedback?.(id, next)
  }

  function handleCopy() {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={`msg ${role}`}>
      <div className="msg-av">
        {role === 'user' ? 'U' : 'S'}
      </div>
      <div className="msg-body">
        <div className="msg-name">{role === 'user' ? 'You' : 'StudyGPT'}</div>
        <div className="msg-text">
          {role === 'assistant'
            ? isStreaming
              ? <span className="stream-text">{text}<span className="stream-cursor" /></span>
              : <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
            : <span>{text}</span>
          }
        </div>

        {sources && sources.length > 0 && (
          <div className="sources">
            {sources.map((s, i) => (
              <span
                key={i}
                className={`src${s.includes('page') ? ' src-clickable' : ''}`}
                onClick={() => s.includes('page') && onSourceClick?.(s)}
                title={s.includes('page') ? 'Click to preview this page' : undefined}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                {s}
              </span>
            ))}
          </div>
        )}

        {role === 'assistant' && !isStreaming && confidence && (
          <div className={`conf-badge conf-${confidence}`}>
            {confidence === 'high' ? '● High confidence' : confidence === 'medium' ? '◑ Medium confidence' : '○ Low confidence'}
          </div>
        )}

        {role === 'assistant' && !isStreaming && followups && followups.length > 0 && (
          <div className="followups">
            <div className="followups-label">Follow-up questions</div>
            <div className="followup-chips">
              {followups.map((q, i) => (
                <button key={i} className="followup-chip" onClick={() => onFollowup?.(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {role === 'assistant' && (
          <div className="feedback-row">
            <button className={`fb-btn${voted === 1 ? ' fb-active-up' : ''}`} onClick={() => handleVote(1)} title="Good answer"><ThumbUp /></button>
            <button className={`fb-btn${voted === -1 ? ' fb-active-down' : ''}`} onClick={() => handleVote(-1)} title="Bad answer"><ThumbDown /></button>
            <button className="fb-btn" onClick={handleCopy} title="Copy">{copied ? <CheckIcon /> : <CopyIcon />}</button>
          </div>
        )}
      </div>
    </div>
  )
}

function ThumbUp() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
}
function ThumbDown() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>
}
function CopyIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
}
function CheckIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
}
