import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const PROMPT_CARDS = [
  { title: 'Summarize key concepts', sub: 'From my uploaded notes', text: 'Summarize the key concepts from my notes' },
  { title: 'Explain in simple terms', sub: 'Any topic from the material', text: 'Explain this topic in simple terms' },
  { title: 'Important formulas', sub: 'To remember for the exam', text: 'What are the important formulas I should remember for the exam?' },
  { title: 'Quiz me', sub: 'Test my understanding with 5 questions', text: 'Quiz me on this chapter with 5 questions' },
]

export default function ChatArea({ messages, loading, onPromptSelect }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const showWelcome = messages.length === 0 && !loading

  return (
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
          <Message key={i} {...msg} />
        ))}

        {loading && (
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
  )
}

function Message({ role, text, sources }) {
  return (
    <div className={`msg ${role}`}>
      <div className="msg-av">
        {role === 'user' ? 'U' : 'S'}
      </div>
      <div className="msg-body">
        <div className="msg-name">{role === 'user' ? 'You' : 'StudyGPT'}</div>
        <div className="msg-text">
          {role === 'assistant'
            ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
            : <span>{text}</span>
          }
        </div>
        {sources && sources.length > 0 && (
          <div className="sources">
            {sources.map((s, i) => (
              <span key={i} className="src">{s}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
