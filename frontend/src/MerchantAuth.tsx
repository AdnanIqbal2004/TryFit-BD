import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, postJson, previewHash } from './merchantApi'
import type { ActionMessage, Session } from './merchantApi'

type Mode = 'login' | 'register' | 'forgot' | 'resend'
type Props = { session: Session | null; onSession: (value: Session) => void; route: string }
const modeLabels = { login: 'Sign in', register: 'Create account', forgot: 'Send reset link', resend: 'Send verification link' }
const minimumPasswordLength = 8

export default function MerchantAuth({ session, onSession, route }: Props) {
  const [mode, setMode] = useState<Mode>(route === '#sign-up' ? 'register' : 'login')
  const [message, setMessage] = useState<ActionMessage | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [accountType, setAccountType] = useState<'customer' | 'merchant'>('customer')
  const [showPassword, setShowPassword] = useState(false)
  const [action, search = ''] = route.split('?')
  const token = new URLSearchParams(search).get('token')
  const verify = action === '#verify-email'
  const reset = action === '#reset-password'
  const invite = action === '#accept-invite'
  const ownerSetup = action === '#owner-setup'
  const ownerSignIn = action === '#platform'
  const actionPage = verify || reset || invite || ownerSetup
  const needsName = ownerSetup || (!actionPage && mode === 'register') || (invite && !session)
  const needsPassword = ownerSetup || reset || (invite && !session) || (!actionPage && (mode === 'register' || mode === 'login'))
  const createsPassword = ownerSetup || reset || invite || mode === 'register'

  function changeMode(next: Mode) {
    setMode(next)
    setShowPassword(false)
    setMessage(null)
    setError('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    setBusy(true)
    setShowPassword(false)
    setError('')
    setMessage(null)
    try {
      if (actionPage) {
        if (!token) throw new Error('Open a valid link to continue.')
        const endpoint = ownerSetup ? 'platform-setup' : verify ? 'verify-email' : reset ? 'password-reset/confirm' : 'invitations/accept'
        const result = await api<ActionMessage>('/api/auth/' + endpoint, postJson({ ...values, token }))
        if (invite) {
          onSession(await api<Session>('/api/auth/me'))
          window.location.replace('#merchant')
          return
        }
        changeMode('login')
        setMessage(result)
        window.history.replaceState(null, '', ownerSetup ? '#platform' : '#merchant')
        window.dispatchEvent(new HashChangeEvent('hashchange'))
      } else if (mode === 'login') {
        onSession(await api<Session>(ownerSignIn ? '/api/auth/platform-login' : '/api/auth/login', postJson(values)))
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

  const title = ownerSetup ? 'Create owner account' : ownerSignIn && mode === 'login' ? 'Owner sign in' : verify ? 'Verify your email' : reset ? 'Set a new password' : invite ? 'Join the workspace' : modeLabels[mode]
  const developmentLink = previewHash(message?.preview_url)

  return (
    <main className="merchant-auth site-width">
      <div className="merchant-auth-intro">
        <p className="eyebrow"><span aria-hidden="true" /> TryFit BD accounts</p>
        {ownerSetup || ownerSignIn ? <>
          <h1>Platform <em>owner.</em></h1>
          <p>See accounts and activity across TryFit BD.</p>
        </> : <>
          <h1>Find your <em>fit.</em></h1>
          <p>Try an outfit in your personal fitting room or manage try-on previews for your store.</p>
        </>}
      </div>
      <div className="merchant-card auth-card">
        {!actionPage && !ownerSignIn && <div className="auth-switch" aria-label="Account options">
          <a href="#sign-in" aria-current={mode === 'login' ? 'page' : undefined} onClick={() => changeMode('login')}>Sign in</a>
          <a href="#sign-up" aria-current={mode === 'register' ? 'page' : undefined} onClick={() => changeMode('register')}>Sign up</a>
        </div>}
        <h2>{title}</h2>
        {ownerSetup && <p>Use an email address you haven’t registered on TryFit BD.</p>}
        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {message && <div className="notice" role="status">
          <p>{message.message}</p>
          {developmentLink && <a href={developmentLink}>Open development link</a>}
        </div>}
        <form className="merchant-fields" onSubmit={submit} key={actionPage ? action : mode}>
          {needsName && <label>Full name<input name="full_name" autoComplete="name" required minLength={2} maxLength={120} /></label>}
          {!actionPage && mode === 'register' && <fieldset className="profile-types">
            <legend>Account type</legend>
            <label><input className="visually-hidden" type="radio" name="account_type" value="customer" checked={accountType === 'customer'} onChange={() => setAccountType('customer')} /><span>Customer<small>Personal try-on</small></span></label>
            <label><input className="visually-hidden" type="radio" name="account_type" value="merchant" checked={accountType === 'merchant'} onChange={() => setAccountType('merchant')} /><span>Merchant<small>Manage a store</small></span></label>
          </fieldset>}
          {!actionPage && mode === 'register' && accountType === 'merchant' && <label>Business name<input name="business_name" autoComplete="organization" required minLength={2} maxLength={120} /></label>}
          {(!actionPage || ownerSetup) && <label>Email address<input type="email" name="email" autoComplete="email" required maxLength={254} /></label>}
          {needsPassword && <div className="password-field">
            <label htmlFor="account-password">{reset ? 'New password' : 'Password'}</label>
            <div className="password-control">
              <input id="account-password" type={showPassword ? 'text' : 'password'} name="password" autoComplete={createsPassword ? 'new-password' : 'current-password'} required minLength={createsPassword ? minimumPasswordLength : undefined} maxLength={256} aria-describedby={createsPassword ? 'password-hint' : undefined} />
              <button type="button" className="password-toggle" aria-controls="account-password" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword(value => !value)}>{showPassword ? 'Hide' : 'Show'}</button>
            </div>
            {createsPassword && <small id="password-hint">Use at least {minimumPasswordLength} characters.</small>}
          </div>}
          <button type="submit" className="button button-primary" disabled={busy}>{busy ? 'Please wait…' : title}</button>
        </form>
        {mode === 'login' && !actionPage && <div className="auth-help">
          <button type="button" className="text-link" onClick={() => changeMode('forgot')}>Forgot password?</button>
          {!ownerSignIn && <button type="button" className="text-link" onClick={() => changeMode('resend')}>Resend verification</button>}
        </div>}
        {ownerSignIn && mode !== 'login' && <button type="button" className="text-link auth-help" onClick={() => changeMode('login')}>Back to owner sign in</button>}
        {actionPage && <a className="text-link auth-help" href={ownerSetup ? '#platform' : '#merchant'}>Back to sign in</a>}
      </div>
    </main>
  )
}
