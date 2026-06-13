import { useState, useEffect } from 'react'

export default function Documents({ onBack }) {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)

  useEffect(() => { loadDocs() }, [])

  async function loadDocs() {
    setLoading(true)
    const res = await fetch('/documents')
    if (res.ok) setDocs(await res.json())
    setLoading(false)
  }

  async function handleDelete(filename) {
    if (!confirm(`Delete "${filename}" and remove it from the knowledge base?`)) return
    setDeleting(filename)
    const res = await fetch(`/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' })
    if (res.ok) setDocs(prev => prev.filter(d => d.filename !== filename))
    setDeleting(null)
  }

  return (
    <div className="view-page">
      <div className="view-header">
        <button className="back-btn" onClick={onBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          Back
        </button>
        <h2 className="view-title">Documents</h2>
      </div>

      {loading ? (
        <div className="view-loading">Loading documents…</div>
      ) : docs.length === 0 ? (
        <div className="view-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.3, marginBottom: 12 }}><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <p>No documents uploaded yet.</p>
          <p style={{ fontSize: 13, color: 'var(--sub)', marginTop: 6 }}>Upload PDFs or images from the chat view.</p>
        </div>
      ) : (
        <div className="doc-list-wrap">
          {docs.map(doc => (
            <div key={doc.filename} className="doc-row">
              <div className="doc-row-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              </div>
              <div className="doc-row-info">
                <div className="doc-row-name">{doc.filename}</div>
                <div className="doc-row-meta">
                  {doc.size_kb} KB · {doc.indexed ? <span style={{ color: 'var(--acc)' }}>Indexed</span> : <span style={{ color: 'var(--sub)' }}>Not indexed</span>}
                </div>
              </div>
              <button
                className="doc-del-btn"
                onClick={() => handleDelete(doc.filename)}
                disabled={deleting === doc.filename}
                title="Delete"
              >
                {deleting === doc.filename ? '…' : (
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
