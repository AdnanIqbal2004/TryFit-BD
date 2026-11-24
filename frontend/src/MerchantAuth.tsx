import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, postJson, previewHash } from './merchantApi'
import type { ActionMessage, Session } from './merchantApi'

type Mode = 'login' | 'register' | 'forgot' | 'resend'
type Props = { session: Session | null; onSession: (value: Session) => void; route: string }
const modeLabels = { login: 'Sign in', register: 'Create account', forgot: 'Send reset link', resend: 'Send verification link' }

export default function MerchantAuth({ session, onSession, route }: Props) {
  const [mode, setMode] = useState<Mode>(route === '#sign-up' ? 'register' : 'login')
  const [message, setMessage] = useState<ActionMessage | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [action, search = ''] = route.split('?')
  const token = new URLSearchParams(search).get('token')
  const verify = action === '#verify-email'
  const reset = action === '#reset-password'
  const invite = action === '#accept-invite'
  const actionPage = verify || reset || invite
  const needsName = (!actionPage && mode === 'register') || (invite && !session)
  const needsPassword = reset || (invite && !session) || (!actionPage && (mode === 'register' || mode === 'login'))

  function changeMode(next: Mode) {
    setMode(next)
    setMessage(null)
    setError('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    setBusy(true)
    setError('')
    setMessage(null)
    try {
      if (actionPage) {
        if (!token) throw new Error('Open a valid link to continue.')
        const endpoint = verify ? 'verify-email' : reset ? 'password-reset/confirm' : 'invitations/accept'
        const result = await api<ActionMessage>('/api/auth/' + endpoint, postJson({ ...values, token }))
        if (invite) {
          onSession(await api<Session>('/api/auth/me'))
          window.location.replace('#merchant')
          return
        }
        changeMode('login')
        setMessage(result)
        window.history.replaceState(null, '', '#merchant')
        window.dispatchEvent(new HashChangeEvent('hashchange'))
      } else if (mode === 'login') {
        onSession(await api<Session>('/api/auth/login', postJson(values)))
      } else {
        const endpoint = mode === 'register' ? 'register' : mode === 'forgot' ? 'password-reset/request' : 'resend-verification'
        setMessage(await api<ActionMessage>('/api/auth/' + endpoint, postJson(values)))
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  const title = verify ? 'Verify your email' : reset ? 'Set a new password' : invite ? 'Join the workspace' : modeLabels[mode]
  const developmentLink = previewHash(message?.preview_url)

  return (
    <main className="merchant-auth site-width">
      <div className="merchant-auth-intro">
        <p className="eyebrow"><span aria-hidden="true" /> For fashion retailers</p>
        <h1>TryFit merchant <em>studio.</em></h1>
        <p>Manage your stores, your team, and the try-on jobs created in your workspace.</p>
      </div>
      <div className="merchant-card auth-card">
        {!actionPage && <div className="auth-switch" aria-label="Account options">
          <a href="#sign-in" aria-current={mode === 'login' ? 'page' : undefined} onClick={() => changeMode('login')}>Sign in</a>
          <a href="#sign-up" aria-current={mode === 'register' ? 'page' : undefined} onClick={() => changeMode('register')}>Sign up</a>
        </div>}
        <h2>{title}</h2>
        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {message && <div className="notice" role="status">
          <p>{message.message}</p>
          {developmentLink && <a href={developmentLink}>Open development link</a>}
        </div>}
        <form className="merchant-fields" onSubmit={submit} key={actionPage ? action : mode}>
          {needsName && <label>Full name<input name="full_name" autoComplete="name" required minLength={2} maxLength={120} /></label>}
          {!actionPage && mode === 'register' && <label>Business name<input name="business_name" autoComplete="organization" required minLength={2} maxLength={120} /></label>}
          {!actionPage && <label>Email address<input type="email" name="email" autoComplete="email" required maxLength={254} /></label>}
          {needsPassword && <label>{reset ? 'New password' : 'Password'}<input type="password" name="password" autoComplete={!actionPage && mode === 'login' ? 'current-password' : 'new-password'} required minLength={!actionPage && mode === 'login' ? undefined : 12} maxLength={256} /></label>}
          <button type="submit" className="button button-primary" disabled={busy}>{busy ? 'Please wait…' : title}</button>
        </form>
        {mode === 'login' && !actionPage && <div className="auth-help">
          <button type="button" className="text-link" onClick={() => changeMode('forgot')}>Forgot password?</button>
          <button type="button" className="text-link" onClick={() => changeMode('resend')}>Resend verification</button>
        </div>}
        {actionPage && <a className="text-link auth-help" href="#merchant">Back to sign in</a>}
      </div>
    </main>
  )
}
