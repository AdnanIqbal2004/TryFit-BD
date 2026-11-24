import { useEffect, useState } from 'react'
import MerchantAuth from './MerchantAuth'
import MerchantDashboard from './MerchantDashboard'
import { api } from './merchantApi'
import type { Session } from './merchantApi'
import './App.css'
import './Merchant.css'
import editorialPhoto from './assets/tryfit-editorial.webp'
import TryOnForm from './TryOnForm'
import SiteSupport from './SiteSupport'

const steps = [
  { title: 'Add your photo', description: 'Use a clear, front-facing photo with your upper body visible.' },
  { title: 'Choose a garment', description: 'Upload a photo of the top, shirt, or cardigan you want to try.' },
  { title: 'Preview your look', description: 'See how the garment might look on you in an AI-generated image.' },
]

function App() {
  const [route, setRoute] = useState(window.location.hash)
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [selectedWorkspace, setSelectedWorkspace] = useState('')
  const workspaceId = session?.workspaces.find(item => item.id === selectedWorkspace)?.id ?? session?.workspaces[0]?.id
  const accountAction = ['#verify-email', '#reset-password', '#accept-invite'].includes(route.split('?')[0])
  const merchant = ['#merchant', '#sign-in', '#sign-up'].includes(route) || accountAction

  useEffect(() => {
    const updateRoute = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', updateRoute)
    const request = new AbortController()
    api<Session>('/api/auth/me', { signal: request.signal })
      .then(value => { if (!request.signal.aborted) setSession(value) })
      .catch(() => { if (!request.signal.aborted) setSession(null) })
    return () => {
      window.removeEventListener('hashchange', updateRoute)
      request.abort()
    }
  }, [])

  useEffect(() => {
    const id = merchant ? 'home' : route.slice(1)
    if (!id) return
    const frame = requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView())
    return () => cancelAnimationFrame(frame)
  }, [merchant, route])

  return (
    <div className="website" id="home">
      <header className="site-header">
        <div className="site-width header-inner">
          <a href="#home" className="brand">TryFit<span>BD</span></a>
          <nav className="nav-links" aria-label="Main navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#try-on">Try it on</a>
            <a href="#contact">Contact</a>
          </nav>
          <div className="header-actions account-nav">
            {session ? <a href="#merchant" className="button button-outline header-cta">Workspace <span aria-hidden="true">↗</span></a> : <>
              <a href="#sign-in" className="text-link">Sign in</a>
              <a href="#sign-up" className="button button-primary header-cta">Sign up</a>
            </>}
          </div>
        </div>
      </header>

      {merchant ? (
        session === undefined ? <main className="site-width account-loading" role="status">Loading your account…</main>
          : session && workspaceId && !accountAction
            ? <MerchantDashboard key={workspaceId} session={session} workspaceId={workspaceId} onWorkspace={setSelectedWorkspace} onSignOut={() => { setSession(null); setSelectedWorkspace('') }} />
            : <MerchantAuth key={route === '#sign-up' ? 'register' : 'account'} session={session} onSession={setSession} route={route} />
      ) : <main>
        <section className="hero site-width" aria-labelledby="hero-title">
          <div className="hero-content">
            <p className="eyebrow"><span aria-hidden="true" /> Virtual try-on</p>
            <h1 id="hero-title">Try before<br />you <em>buy.</em></h1>
            <p className="hero-description">See how a top might look on you before you shop. Upload your photo, choose a garment, and let AI build the preview.</p>
            <a href="#try-on" className="button button-primary">Open the fitting room <span aria-hidden="true">↗</span></a>
            <a href="#how-it-works" className="text-link">How it works <span aria-hidden="true">↓</span></a>
          </div>
          <figure className="hero-visual">
            <img src={editorialPhoto} alt="Fashion editorial featuring a burgundy jacket" fetchPriority="high" />
          </figure>
        </section>

        {workspaceId ? <TryOnForm key={workspaceId} workspaceId={workspaceId} /> : (
          <section className="studio" id="try-on" aria-labelledby="try-on-title">
            <div className="site-width gated-studio">
              <div><h2 id="try-on-title">The fitting room</h2><p>Sign in to create a try-on preview in your merchant workspace.</p></div>
              <a href="#merchant" className="button button-primary">Open merchant studio ↗</a>
            </div>
          </section>
        )}

        <section className="how-section site-width" id="how-it-works" aria-labelledby="how-title">
          <h2 id="how-title">How it works</h2>
          <ol className="steps">
            {steps.map((step, index) => (
              <li key={step.title}>
                <span className="step-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </li>
            ))}
          </ol>
        </section>
        <SiteSupport />
      </main>}

      <footer className="site-footer" id="about">
        <div className="site-width footer-inner">
          <a href="#home" className="brand">TryFit<span>BD</span></a>
          <p>An academic virtual try-on prototype for online shoppers in Bangladesh.</p>
          <div className="footer-links">
            <a className="text-link" href="#contact">Contact</a>
            <a className="text-link" href="#home">Back to top <span aria-hidden="true">↑</span></a>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
