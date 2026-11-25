import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, postJson, previewHash } from './merchantApi'
import type { ActionMessage, Dashboard, Session } from './merchantApi'

type Tab = 'Overview' | 'Stores' | 'Team' | 'API keys'
const tabs: Tab[] = ['Overview', 'Stores', 'Team', 'API keys']

type Props = {
  session: Session
  workspaceId: string
}

export default function MerchantDashboard({ session, workspaceId }: Props) {
  const [tab, setTab] = useState<Tab>('Overview')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState<ActionMessage | null>(null)
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const request = new AbortController()
    api<Dashboard>('/api/workspace', { signal: request.signal }, workspaceId)
      .then(data => { if (!request.signal.aborted) setDashboard(data) })
      .catch(cause => { if (!request.signal.aborted) setError(String(cause.message)) })
    return () => request.abort()
  }, [workspaceId])

  async function action(callback: () => Promise<void>) {
    setBusy(true)
    setError('')
    setMessage(null)
    try {
      await callback()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The operation failed.')
    } finally {
      setBusy(false)
    }
  }

  async function refresh() {
    setDashboard(await api<Dashboard>('/api/workspace', {}, workspaceId))
  }

  function remove(path: string, question: string) {
    if (!window.confirm(question)) return
    void action(async () => {
      await api(path, { method: 'DELETE' }, workspaceId)
      setSecret('')
      await refresh()
    })
  }

  function submit(event: FormEvent<HTMLFormElement>, path: string) {
    event.preventDefault()
    const form = event.currentTarget
    const body = Object.fromEntries(new FormData(form))
    void action(async () => {
      const result = await api<ActionMessage & { secret?: string }>(path, postJson(body), workspaceId)
      if (result.secret) setSecret(result.secret)
      if (result.message) setMessage(result)
      form.reset()
      await refresh()
    })
  }

  const workspace = dashboard?.workspace ?? session.workspaces.find(value => value.id === workspaceId)
  const canManage = workspace?.role === 'owner' || workspace?.role === 'admin'
  const developmentLink = previewHash(message?.preview_url)
  const invalidations = error || message
  return (
    <main className="merchant-workspace site-width">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow"><span aria-hidden="true" /> {canManage ? 'Admin workspace' : 'Merchant workspace'}</p>
          <h1>{workspace?.name ?? 'Your workspace'}</h1>
          <p>{session.user.full_name} · {workspace?.role ?? 'Merchant'}</p>
        </div>

      </div>

      <nav className="workspace-nav" aria-label="Workspace sections">
        {tabs.map(item => <button key={item} type="button" aria-pressed={tab === item} disabled={busy} onClick={() => {
          setTab(item)
          setSecret('')
          setError('')
          setMessage(null)
        }}>{item}</button>)}
      </nav>

      {invalidations && <div className={error ? 'notice notice-error' : 'notice'} role={error ? 'alert' : 'status'}>
        <p>{error || message?.message}</p>
        {developmentLink && <a href={developmentLink}>Open development link</a>}
      </div>}
      {!dashboard && !error && <p role="status">Loading your workspace…</p>}
      {dashboard && tab === 'Overview' && <>
        <div className="workspace-metrics">
          <div className="merchant-card"><p>Previews this month</p><strong>{dashboard.usage.this_month}</strong></div>
          <div className="merchant-card"><p>Total previews</p><strong>{dashboard.usage.total}</strong></div>
          <div className="merchant-card"><p>Stores</p><strong>{dashboard.stores.length}</strong></div>
        </div>
        <section className="merchant-card dashboard-panel">
          <div className="panel-heading"><h2>Recent try-on jobs</h2><a className="text-link" href="#try-on">Open fitting room ↗</a></div>
          {dashboard.jobs.length ? <ul className="dashboard-list">{dashboard.jobs.map(job => (
            <li key={job.job_id}><div><strong>{job.category === 'upper' ? 'Upper body' : job.category}</strong><small>{new Date(job.created_at).toLocaleString()}</small></div><span className={'job-status job-' + job.status}>{job.status}{job.processing_seconds !== null ? ' · ' + job.processing_seconds.toFixed(1) + ' s' : ''}</span></li>
          ))}</ul> : <p>No try-on jobs yet.</p>}
        </section>
      </>}

      {dashboard && tab === 'Stores' && <section className="merchant-card dashboard-panel">
        <h2>Stores</h2>
        <p>Add a store record for this workspace. Store records are managed here.</p>
        {canManage && <form className="dashboard-form" onSubmit={event => submit(event, '/api/workspace/stores')}>
          <label>Store name<input name="display_name" required minLength={2} maxLength={100} /></label>
          <label>Store domain<input name="store_domain" placeholder="shop.example.com" required minLength={3} maxLength={253} /></label>
          <label>Platform<select name="provider"><option value="custom">Custom</option><option value="shopify">Shopify</option><option value="woocommerce">WooCommerce</option></select></label>
          <button className="button button-primary" disabled={busy}>Add store</button>
        </form>}
        {dashboard.stores.length ? <ul className="dashboard-list">{dashboard.stores.map(store => (
          <li key={store.id}><div><strong>{store.display_name}</strong><small>{store.store_domain} · {store.provider}</small></div>
            {canManage && <button type="button" className="text-link" disabled={busy} onClick={() => remove('/api/workspace/stores/' + encodeURIComponent(store.id), 'Remove this store record?')}>Remove</button>}
          </li>
        ))}</ul> : <p>No stores added yet.</p>}
      </section>}

      {dashboard && tab === 'Team' && <section className="merchant-card dashboard-panel">
        <h2>Workspace team</h2>
        {canManage && <form className="dashboard-form" onSubmit={event => submit(event, '/api/workspace/invitations')}>
          <label>Invite email<input type="email" name="email" required /></label>
          <label>Role<select name="role"><option value="member">Member</option>{workspace?.role === 'owner' && <option value="admin">Admin</option>}</select></label>
          <button className="button button-primary" disabled={busy}>Invite member</button>
        </form>}
        <ul className="dashboard-list">{dashboard.members.map(member => (
          <li key={member.id}><div><strong>{member.full_name}</strong><small>{member.email}</small></div><span>{member.role}</span></li>
        ))}</ul>
        {dashboard.invitations.length > 0 && <><h3>Pending invitations</h3><ul className="dashboard-list">{dashboard.invitations.map(invite => (
          <li key={invite.email}><div><strong>{invite.email}</strong><small>{invite.role}</small></div>
            {canManage && <button type="button" className="text-link" disabled={busy} onClick={() => remove('/api/workspace/invitations/' + encodeURIComponent(invite.email), 'Cancel this invitation?')}>Cancel</button>}
          </li>
        ))}</ul></>}
      </section>}

      {dashboard && tab === 'API keys' && <section className="merchant-card dashboard-panel">
        <h2>API keys</h2>
        <p>Use a workspace key from your server when calling the TryFit BD API.</p>
        {canManage && <form className="dashboard-form" onSubmit={event => submit(event, '/api/workspace/api-keys')}>
          <label>Key name<input name="name" required minLength={2} maxLength={80} /></label>
          <button className="button button-primary" disabled={busy}>Create key</button>
        </form>}
        {secret && <div className="notice secret-panel"><code>{secret}</code><button className="text-link" type="button" onClick={() => setSecret('')}>Hide key</button></div>}
        {dashboard.api_keys.length ? <ul className="dashboard-list">{dashboard.api_keys.map(key => (
          <li key={key.id}><div><strong>{key.name}</strong><small>{key.prefix}</small></div>
            {canManage && <button type="button" className="text-link" disabled={busy} onClick={() => remove('/api/workspace/api-keys/' + encodeURIComponent(key.id), 'Revoke this API key? Requests using it will stop working.')}>Revoke</button>}
          </li>
        ))}</ul> : <p>No active API keys.</p>}
      </section>}
    </main>
  )
}
