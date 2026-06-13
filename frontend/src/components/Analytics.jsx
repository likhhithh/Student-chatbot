import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'

export default function Analytics({ userId, onBack }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!userId) return
    async function load() {
      const { data: chats } = await supabase
        .from('chats').select('id').eq('user_id', userId)

      if (!chats?.length) {
        setStats({ totalChats: 0, totalMessages: 0, thumbsUp: 0, thumbsDown: 0, daily: [], topics: [] })
        setLoading(false)
        return
      }

      const chatIds = chats.map(c => c.id)
      const [msgRes, topicRes] = await Promise.all([
        supabase.from('messages').select('role, feedback, created_at').in('chat_id', chatIds),
        supabase.from('user_memory').select('topic').eq('user_id', userId).order('created_at', { ascending: false }).limit(10),
      ])

      const msgs = msgRes.data || []
      const topics = (topicRes.data || []).map(t => t.topic)
      const thumbsUp = msgs.filter(m => m.feedback === 1).length
      const thumbsDown = msgs.filter(m => m.feedback === -1).length

      const daily = []
      for (let i = 6; i >= 0; i--) {
        const d = new Date()
        d.setDate(d.getDate() - i)
        const dateStr = d.toISOString().slice(0, 10)
        const label = d.toLocaleDateString('en', { weekday: 'short' })
        const count = msgs.filter(m => m.created_at?.slice(0, 10) === dateStr).length
        daily.push({ label, count })
      }

      setStats({ totalChats: chats.length, totalMessages: msgs.length, thumbsUp, thumbsDown, daily, topics })
      setLoading(false)
    }
    load()
  }, [userId])

  const maxDaily = stats ? Math.max(...stats.daily.map(d => d.count), 1) : 1
  const satisfaction = stats && (stats.thumbsUp + stats.thumbsDown) > 0
    ? Math.round((stats.thumbsUp / (stats.thumbsUp + stats.thumbsDown)) * 100)
    : null

  return (
    <div className="view-page">
      <div className="view-header">
        <button className="back-btn" onClick={onBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          Back
        </button>
        <h2 className="view-title">Analytics</h2>
      </div>

      {loading ? (
        <div className="view-loading">Loading stats…</div>
      ) : (
        <div className="analytics-body">
          <div className="stat-cards">
            <div className="stat-card">
              <div className="stat-val">{stats.totalChats}</div>
              <div className="stat-lbl">Conversations</div>
            </div>
            <div className="stat-card">
              <div className="stat-val">{stats.totalMessages}</div>
              <div className="stat-lbl">Total Messages</div>
            </div>
            <div className="stat-card">
              <div className="stat-val" style={{ color: '#10a37f' }}>{stats.thumbsUp}</div>
              <div className="stat-lbl">👍 Helpful</div>
            </div>
            <div className="stat-card">
              <div className="stat-val" style={{ color: '#dc2626' }}>{stats.thumbsDown}</div>
              <div className="stat-lbl">👎 Not helpful</div>
            </div>
          </div>

          {satisfaction !== null && (
            <div className="analytics-section">
              <div className="section-title">Satisfaction rate</div>
              <div className="satisfaction-bar-wrap">
                <div className="satisfaction-bar" style={{ width: `${satisfaction}%` }} />
                <span className="satisfaction-pct">{satisfaction}%</span>
              </div>
            </div>
          )}

          <div className="analytics-section">
            <div className="section-title">Messages — last 7 days</div>
            <div className="bar-chart">
              {stats.daily.map((d, i) => (
                <div key={i} className="bar-col">
                  <div className="bar-wrap">
                    <div className="bar" style={{ height: `${Math.round((d.count / maxDaily) * 100)}%` }} />
                  </div>
                  <div className="bar-lbl">{d.label}</div>
                  <div className="bar-val">{d.count}</div>
                </div>
              ))}
            </div>
          </div>

          {stats.topics.length > 0 && (
            <div className="analytics-section">
              <div className="section-title">Recent topics studied</div>
              <div className="topic-list">
                {stats.topics.map((t, i) => (
                  <span key={i} className="topic-chip">{t}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
