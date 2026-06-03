import { useState, useRef, useCallback, useEffect } from 'react'

function fileIcon(name) {
  const ext = (name.split('.').pop() || '').toLowerCase()
  if (ext === 'pdf') return 'PDF'
  if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return 'IMG'
  return 'FILE'
}

export default function InputZone({ onSend, loading, pendingPrompt, onPromptConsumed }) {
  const [text, setText] = useState('')
  const [attached, setAttached] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  const [uploadLabel, setUploadLabel] = useState('')
  const fileRef = useRef(null)
  const taRef = useRef(null)

  useEffect(() => {
    if (pendingPrompt) {
      setText(pendingPrompt)
      onPromptConsumed?.()
      setTimeout(() => { autoResize(); taRef.current?.focus() }, 0)
    }
  }, [pendingPrompt, onPromptConsumed])

  const canSend = (text.trim() || attached.length > 0) && !loading && !uploading

  const autoResize = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSend) handleSend()
    }
  }

  const handleFiles = (e) => {
    const files = Array.from(e.target.files)
    setAttached(prev => {
      const next = [...prev]
      files.forEach(f => { if (!next.find(x => x.name === f.name)) next.push(f) })
      return next
    })
    e.target.value = ''
  }

  const removeFile = (i) => setAttached(prev => prev.filter((_, idx) => idx !== i))

  const handleSend = useCallback(async () => {
    if (!canSend) return
    const q = text.trim()
    setText('')
    if (taRef.current) taRef.current.style.height = 'auto'

    if (attached.length > 0) {
      setUploading(true)
      setUploadPct(20)
      setUploadLabel('Uploading files…')
    }

    try {
      await onSend(q, attached)
    } finally {
      setAttached([])
      setUploading(false)
      setUploadPct(0)
    }
  }, [canSend, text, attached, onSend])

  return (
    <div className="input-zone">
      <div className="input-inner">
        {attached.length > 0 && (
          <div className="file-pills">
            {attached.map((f, i) => (
              <div key={i} className="file-pill">
                {fileIcon(f.name)}
                <span style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                <span className="rm-pill" onClick={() => removeFile(i)}>×</span>
              </div>
            ))}
          </div>
        )}

        {uploading && (
          <div className="up-progress">
            <div className="dots"><div className="dot" /><div className="dot" /><div className="dot" /></div>
            <span>{uploadLabel}</span>
            <div className="prog-bar-wrap"><div className="prog-bar" style={{ width: uploadPct + '%' }} /></div>
          </div>
        )}

        <div className="ibox">
          <textarea
            ref={taRef}
            rows={1}
            placeholder="Ask anything about your uploaded documents…"
            value={text}
            onChange={e => { setText(e.target.value); autoResize() }}
            onKeyDown={handleKey}
          />
          <div className="ibox-btns">
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              style={{ display: 'none' }}
              onChange={handleFiles}
            />
            <button className="ibtn attach" onClick={() => fileRef.current?.click()} title="Attach PDF or image">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
              </svg>
            </button>
            <button className="ibtn send" disabled={!canSend} onClick={handleSend} title="Send">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </div>
        </div>

        <div className="hint">Press Enter to send · Shift+Enter for new line · Attach PDF or images</div>
      </div>
    </div>
  )
}
