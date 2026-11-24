export type Workspace = { id: string; name: string; role: 'owner' | 'admin' | 'member' }
export type Session = {
  user: { id: string; full_name: string; email: string }
  workspaces: Workspace[]
}
export type ActionMessage = { message: string; preview_url?: string | null }
export type Dashboard = {
  user: Session['user']
  workspace: Workspace
  workspaces: Workspace[]
  stores: { id: string; display_name: string; store_domain: string; provider: string }[]
  api_keys: { id: string; name: string; prefix: string }[]
  members: { id: string; full_name: string; email: string; role: Workspace['role'] }[]
  invitations: { email: string; role: string }[]
  jobs: { job_id: string; status: string; category: string; created_at: string; processing_seconds: number | null }[]
  usage: { total: number; this_month: number }
}

export async function api<T>(path: string, options: RequestInit = {}, workspaceId?: string): Promise<T> {
  const headers = new Headers(options.headers)
  if (workspaceId) headers.set('X-Organization-Id', workspaceId)
  const response = await fetch(path, { cache: 'no-store', ...options, headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail[0]?.msg : undefined
    throw new Error(message ?? 'The request could not be completed.')
  }
  return response.status === 204 ? undefined as T : response.json()
}

export function postJson(body?: object): RequestInit {
  return body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { method: 'POST' }
}

export function previewHash(url?: string | null) {
  if (!url) return ''
  try {
    const hash = new URL(url, window.location.origin).hash
    return /^#(verify-email|reset-password|accept-invite)\?token=/.test(hash) ? hash : ''
  } catch {
    return ''
  }
}
