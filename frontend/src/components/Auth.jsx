import { useState } from 'react'
import { supabase } from '../lib/supabase'

const TABS = ['magic', 'password', 'google']

export default function Auth() {
  const [tab, setTab]         = useState('magic')
  const [email, setEmail]     = useState('')
  const [password, setPass]   = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg]         = useState(null) // { text, ok }

  function flash(text, ok = true) { setMsg({ text, ok }) }
  function clearMsg() { setMsg(null) }

  async function handleGoogle() {
    setLoading(true); clearMsg()
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })
    if (error) flash(error.message, false)
    setLoading(false)
  }

  async function handleMagicLink(e) {
    e.preventDefault()
    if (!email.trim()) return flash('Enter your email address.', false)
    setLoading(true); clearMsg()
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    })
    if (error) flash(error.message, false)
    else flash('Check your inbox — magic link sent!')
    setLoading(false)
  }

  async function handlePassword(e) {
    e.preventDefault()
    if (!email.trim() || !password) return flash('Enter email and password.', false)
    setLoading(true); clearMsg()
    // Try sign-in first; if user not found, sign them up
    const { error: signInErr } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    if (signInErr) {
      if (signInErr.message.toLowerCase().includes('invalid login') ||
          signInErr.message.toLowerCase().includes('no user')) {
        const { error: signUpErr } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: window.location.origin },
        })
        if (signUpErr) flash(signUpErr.message, false)
        else flash('Account created! Check your inbox to confirm your email.')
      } else {
        flash(signInErr.message, false)
      }
    }
    setLoading(false)
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        {/* Logo */}
        <div style={s.logoRow}>
          <img src="/studygpt-logo.png" alt="StudyGPT" style={s.logoImg} />
        </div>

        <h1 style={s.h1}>Welcome to StudyGPT</h1>
        <p style={s.sub}>Sign in to your account to continue</p>

        {/* Google */}
        <button style={s.googleBtn} onClick={handleGoogle} disabled={loading}>
          <GoogleIcon />
          Continue with Google
        </button>

        <div style={s.dividerRow}>
          <div style={s.divLine} />
          <span style={s.divText}>or</span>
          <div style={s.divLine} />
        </div>

        {/* Tab switcher */}
        <div style={s.tabs}>
          <button
            style={{ ...s.tab, ...(tab === 'magic' ? s.tabActive : {}) }}
            onClick={() => { setTab('magic'); clearMsg() }}
          >Magic Link</button>
          <button
            style={{ ...s.tab, ...(tab === 'password' ? s.tabActive : {}) }}
            onClick={() => { setTab('password'); clearMsg() }}
          >Email &amp; Password</button>
        </div>

        {/* Magic link form */}
        {tab === 'magic' && (
          <form onSubmit={handleMagicLink} style={s.form}>
            <label style={s.label}>Email address</label>
            <input
              style={s.input}
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoFocus
            />
            <p style={s.hint}>We'll send a one-click sign-in link to your inbox — no password needed.</p>
            <button style={s.submitBtn} type="submit" disabled={loading}>
              {loading ? 'Sending…' : 'Send magic link'}
            </button>
          </form>
        )}

        {/* Email + password form */}
        {tab === 'password' && (
          <form onSubmit={handlePassword} style={s.form}>
            <label style={s.label}>Email address</label>
            <input
              style={s.input}
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoFocus
            />
            <label style={{ ...s.label, marginTop: 12 }}>Password</label>
            <input
              style={s.input}
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPass(e.target.value)}
            />
            <p style={s.hint}>New here? We'll create your account automatically.</p>
            <button style={s.submitBtn} type="submit" disabled={loading}>
              {loading ? 'Please wait…' : 'Sign in / Sign up'}
            </button>
          </form>
        )}

        {/* Flash message */}
        {msg && (
          <div style={{ ...s.flash, ...(msg.ok ? s.flashOk : s.flashErr) }}>
            {msg.text}
          </div>
        )}

        <p style={s.footer}>
          By continuing, you agree to our{' '}
          <span style={s.flink}>Terms of Service</span> and{' '}
          <span style={s.flink}>Privacy Policy</span>.
        </p>
      </div>
    </div>
  )
}

/* ── Inline styles (self-contained, no CSS class conflicts) ── */
const s = {
  page: {
    minHeight: '100vh',
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #f0fdf9 0%, #ffffff 50%, #f8fafc 100%)',
    padding: '24px 16px',
  },
  card: {
    background: '#ffffff',
    borderRadius: 20,
    boxShadow: '0 8px 40px rgba(0,0,0,.10)',
    padding: '40px 40px 32px',
    width: '100%',
    maxWidth: 420,
    border: '1px solid #e5e7eb',
  },
  logoRow: {
    display: 'flex',
    justifyContent: 'center',
    marginBottom: 20,
  },
  logoImg: {
    height: 44,
    objectFit: 'contain',
  },
  h1: {
    fontSize: 22,
    fontWeight: 700,
    color: '#111827',
    textAlign: 'center',
    marginBottom: 6,
    letterSpacing: '-0.4px',
  },
  sub: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    marginBottom: 24,
  },
  googleBtn: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    padding: '11px 16px',
    borderRadius: 10,
    border: '1.5px solid #e5e7eb',
    background: '#fff',
    color: '#111827',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background .15s, box-shadow .15s',
    boxShadow: '0 1px 4px rgba(0,0,0,.06)',
    fontFamily: 'inherit',
  },
  dividerRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    margin: '20px 0',
  },
  divLine: { flex: 1, height: 1, background: '#e5e7eb' },
  divText: { fontSize: 12, color: '#9ca3af', fontWeight: 500 },
  tabs: {
    display: 'flex',
    gap: 6,
    marginBottom: 20,
    background: '#f3f4f6',
    borderRadius: 10,
    padding: 4,
  },
  tab: {
    flex: 1,
    padding: '8px 12px',
    border: 'none',
    borderRadius: 8,
    background: 'transparent',
    color: '#6b7280',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background .15s, color .15s',
    fontFamily: 'inherit',
  },
  tabActive: {
    background: '#ffffff',
    color: '#111827',
    boxShadow: '0 1px 4px rgba(0,0,0,.08)',
  },
  form: { display: 'flex', flexDirection: 'column' },
  label: { fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 },
  input: {
    padding: '10px 14px',
    borderRadius: 10,
    border: '1.5px solid #e5e7eb',
    fontSize: 14,
    color: '#111827',
    outline: 'none',
    fontFamily: 'inherit',
    background: '#fff',
    transition: 'border-color .2s, box-shadow .2s',
  },
  hint: { fontSize: 12, color: '#9ca3af', marginTop: 8, marginBottom: 16, lineHeight: 1.5 },
  submitBtn: {
    padding: '11px 16px',
    borderRadius: 10,
    border: 'none',
    background: '#10a37f',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'background .15s',
    marginTop: 4,
  },
  flash: {
    marginTop: 16,
    padding: '10px 14px',
    borderRadius: 10,
    fontSize: 13,
    fontWeight: 500,
    lineHeight: 1.5,
  },
  flashOk:  { background: '#e6f7f3', color: '#10a37f', border: '1px solid #b2e8da' },
  flashErr: { background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca' },
  footer: { fontSize: 11, color: '#9ca3af', textAlign: 'center', marginTop: 20 },
  flink: { color: '#10a37f', cursor: 'pointer', fontWeight: 500 },
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
    </svg>
  )
}
