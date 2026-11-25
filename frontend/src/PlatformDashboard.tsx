import { useEffect, useState } from 'react'
import { api } from './merchantApi'

type Overview = {
  counts: {
    total: number
    customers: number
    merchants: number
    unverified: number
    merchant_workspaces: number
    stores: number
    tryon_requests: number
  }
  accounts: {
    id: string
    full_name: string
    email: string
    kind: 'customer' | 'merchant' | 'unassigned'
    verified: boolean
    created_at: string
  }[]
  page: number
  page_size: number
}

const accountLabels = { customer: 'Customer', merchant: 'Merchant', unassigned: 'Unassigned' }
const countFormatter = new Intl.NumberFormat()
const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

export default function PlatformDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [page, setPage] = useState(1)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const request = new AbortController()
    api<Overview>(`/api/platform/overview?page=${page}`, { signal: request.signal })
      .then(data => {
        if (request.signal.aborted) return
        setOverview(data)
        setLoading(false)
      })
      .catch(cause => {
        if (request.signal.aborted) return
        setOverview(null)
        setError(cause instanceof Error ? cause.message : 'Could not load the dashboard.')
        setLoading(false)
      })
    return () => request.abort()
  }, [page, refresh])

  function loadPage(nextPage: number) {
    setError('')
    setLoading(true)
    if (nextPage === page) setRefresh(value => value + 1)
    else setPage(nextPage)
  }

  const counts = overview?.counts
  const metrics = counts ? [
    { label: 'Total accounts', value: counts.total },
    { label: 'Customer accounts', value: counts.customers },
    { label: 'Merchant accounts', value: counts.merchants },
    { label: 'Pending verification', value: counts.unverified },
  ] : []

  return (
    <main className="site-width merchant-workspace platform-dashboard">
      <div className="workspace-heading">
        <div>
          <h1>Owner dashboard</h1>
          <p>See sign-ups and activity across TryFit BD.</p>
        </div>
        <button className="button button-outline" type="button" disabled={loading} onClick={() => loadPage(page)}>Refresh</button>
      </div>
      {loading && <p className="notice" role="status">Loading platform activity…</p>}
      {error && <p className="notice notice-error" role="alert">{error}</p>}
      {overview && counts && <>
        <div className="workspace-metrics platform-metrics">
          {metrics.map(metric => <div className="merchant-card" key={metric.label}>
            <strong>{countFormatter.format(metric.value)}</strong><p>{metric.label}</p>
          </div>)}
        </div>
        <dl className="platform-activity">
          <div><dt>Merchant workspaces</dt><dd>{countFormatter.format(counts.merchant_workspaces)}</dd></div>
          <div><dt>Registered stores</dt><dd>{countFormatter.format(counts.stores)}</dd></div>
          <div><dt>Try-on requests</dt><dd>{countFormatter.format(counts.tryon_requests)}</dd></div>
        </dl>
        <section className="merchant-card dashboard-panel" aria-labelledby="platform-accounts">
          <div className="panel-heading"><h2 id="platform-accounts">Accounts</h2></div>
          {counts.total === 0 ? <p>No accounts yet.</p> : <>
            <div className="platform-table">
              <table aria-labelledby="platform-accounts">
                <thead><tr><th scope="col">Name</th><th scope="col">Account type</th><th scope="col">Email status</th><th scope="col">Joined</th></tr></thead>
                <tbody>{overview.accounts.map(account => (
                  <tr key={account.id}>
                    <td><strong>{account.full_name}</strong><small>{account.email}</small></td>
                    <td>{accountLabels[account.kind]}</td>
                    <td><span className={`job-status ${account.verified ? 'job-done' : ''}`}>{account.verified ? 'Verified' : 'Pending'}</span></td>
                    <td><time dateTime={account.created_at}>{dateFormatter.format(new Date(account.created_at))}</time></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <nav className="platform-pagination" aria-label="Account pages">
              <button className="button button-outline" type="button" disabled={loading || overview.page === 1} onClick={() => loadPage(overview.page - 1)}>Previous</button>
              <span>Page {overview.page}</span>
              <button className="button button-outline" type="button" disabled={loading || overview.page * overview.page_size >= counts.total} onClick={() => loadPage(overview.page + 1)}>Next</button>
            </nav>
          </>}
        </section>
      </>}
    </main>
  )
}
