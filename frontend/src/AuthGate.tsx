/* DELTA_UNIVERSITY_PRODUCTION_VISUAL_V1 */
import StaffPortal from './StaffPortal'
import { useEffect, useState, type FormEvent } from 'react'
import { CircleAlert, LockKeyhole, LogOut, RefreshCw, ShieldCheck } from './ui/DeltaIcons'
import App from './App'
import { authConfigurationMissing, supabase } from './authClient'
import { getMe, type Me } from './api'
import type { Session } from '@supabase/supabase-js'

export default function AuthGate() {
  const [session, setSession] = useState<Session | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!supabase) { setLoading(false); return }
    let active = true
    supabase.auth.getSession().then(({ data }) => {
      if (active) { setSession(data.session); setLoading(false) }
    }).catch(() => { if (active) { setError('Unable to load session'); setLoading(false) } })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      if (active) {
        setSession(next)
        // Supabase can report SIGNED_IN again when a tab regains focus.
        // Retain the verified identity only for the very same user.
        setMe(current => next && current?.user_id === next.user.id ? current : null)
      }
    })
    return () => { active = false; subscription.unsubscribe() }
  }, [])

  useEffect(() => {
    if (!session) { setMe(null); return }
    let active = true
    setLoading(true)
    getMe().then(value => { if (active) { setMe(value); setError('') } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [session?.user.id, session?.access_token])

  async function login(e: FormEvent) {
    e.preventDefault(); if (!supabase) return
    setSubmitting(true); setError('')
    const { error: loginError } = await supabase.auth.signInWithPassword({email: email.trim(), password})
    if (loginError) setError(loginError.message)
    setSubmitting(false)
  }
  async function logout() { await supabase?.auth.signOut(); setMe(null); setSession(null); setError('') }

  if (authConfigurationMissing) return <div className="login-page"><section className="login-card"><CircleAlert size={28}/><h1>Client configuration required</h1><p>Create <code>.env.local</code> from <code>.env.local.example</code>, with your Supabase Project URL and <b>publishable</b> key. Restart Vite. Never put the secret key here.</p></section></div>
  if (loading) return <div className="login-page"><div className="loading-state"><RefreshCw className="spin"/><h2>Checking your account...</h2></div></div>
  if (session && me?.role === 'admin') return <App onSignOut={logout} accountEmail={me.email || ''}/>
  if (session && me?.role === 'staff') return <StaffPortal me={me} logout={logout}/>
  if (session && !me) return <div className="login-page"><section className="login-card"><CircleAlert size={28}/><h1>Account not authorized</h1><p>{error || 'Your university account is not assigned an application role.'}</p><p>Ask your admin to link your Supabase Auth user ID to <code>system_admins</code> or <code>staff.auth_user_id</code>.</p><button className="outline-button" onClick={logout}><LogOut size={16}/> Sign out</button></section></div>
  return <div className="login-page"><section className="login-card"><div className="login-logo delta-login-logo"><img src="/delta-university-logo.png" alt="Delta University logo"/></div><div className="eyebrow">DELTA UNIVERSITY · SECURE ACCESS</div><h1>Welcome back</h1><p>Sign in with your university exam operations account.</p>
    <form onSubmit={login}><label htmlFor="login-email">Email</label><input id="login-email" type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@university.edu"/>
      <label htmlFor="login-password">Password</label><input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••••"/>
      {error && <p className="form-error"><CircleAlert size={15}/> {error}</p>}
      <button className="login-submit" disabled={submitting} type="submit"><LockKeyhole size={16}/>{submitting ? 'Signing in...' : 'Sign in securely'}</button></form>
    <div className="login-privacy"><ShieldCheck size={16}/> Access is verified on the server. No public registration.</div></section></div>
}
