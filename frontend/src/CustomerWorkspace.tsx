import { useCallback, useEffect, useState } from 'react'
import { api } from './merchantApi'
import type { Dashboard, Session } from './merchantApi'
import TryOnForm from './TryOnForm'

export default function CustomerWorkspace({ session, workspaceId }: { session: Session; workspaceId: string }) {
  const [history, setHistory] = useState<Dashboard['jobs'] | null>(null)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    const request = new AbortController()
    api<{ jobs: Dashboard['jobs'] }>('/api/jobs/history', { signal: request.signal }, workspaceId)
      .then(data => {
        if (request.signal.aborted) return
        setHistory(data.jobs)
        setError('')
      })
      .catch(cause => { if (!request.signal.aborted) setError(cause.message) })
    return () => request.abort()
  }, [workspaceId, revision])

  const refreshHistory = useCallback(() => { setRevision(value => value + 1) }, [])

  return (
    <main>
      <section className="customer-welcome site-width">
        <div>
          <p className="eyebrow"><span aria-hidden="true" /> Customer account</p>
          <h1>Your fitting room.</h1>
          <p>Hi, {session.user.full_name}. See how your next outfit might look on you.</p>
        </div>
        <a href="#try-on" className="button button-primary">Try an outfit <span aria-hidden="true">↓</span></a>
      </section>
      <TryOnForm workspaceId={workspaceId} onJobChange={refreshHistory} />
      <section className="customer-history site-width">
        <div className="merchant-card dashboard-panel">
          <div className="panel-heading"><h2>Recent previews</h2><button type="button" className="text-link" onClick={refreshHistory}>Refresh</button></div>
          {error ? <p className="notice notice-error" role="alert">{error}</p>
            : history === null ? <p role="status">Loading previews…</p>
              : history.length === 0 ? <p>Your try-on jobs will appear here.</p>
                : <ul className="dashboard-list">{history.map(job => (
                  <li key={job.job_id}>
                    <div><strong>Upper-body try-on</strong><small>{new Date(job.created_at).toLocaleString()}</small></div>
                    <span className={'job-status job-' + job.status}>{job.status === 'done' ? 'Ready' : job.status}</span>
                  </li>
                ))}</ul>}
        </div>
      </section>
    </main>
  )
}
