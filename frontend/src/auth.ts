import { reactive } from 'vue'

export interface SessionStatus { enabled: boolean; authenticated: boolean; csrf_token: string | null }
export const humanSession = reactive({ enabled: false, authenticated: false, checking: true, loaded: false, csrf: '', error: '' })

function accept(body: SessionStatus) {
  if (typeof body.enabled !== 'boolean' || typeof body.authenticated !== 'boolean' || (body.enabled && body.authenticated && !body.csrf_token)) throw new Error('Unexpected sign-in response. Try again.')
  Object.assign(humanSession, { enabled: body.enabled, authenticated: body.authenticated, csrf: body.csrf_token ?? '', loaded: true, checking: false, error: '' })
}

async function authRequest(path: string, options: RequestInit = {}): Promise<SessionStatus> {
  const response = await fetch(path, { ...options, cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(8000) })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Sign-in request failed (${response.status})`)
  }
  return response.json()
}

export async function checkHumanSession() {
  humanSession.checking = true
  try { accept(await authRequest('/api/auth/session')) }
  catch (error) { humanSession.error = error instanceof Error ? error.message : 'Unable to reach your workspace.'; humanSession.checking = false }
}

export async function signIn(password: string) {
  accept(await authRequest('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) }))
}

export function withSessionHeaders(options: RequestInit): RequestInit {
  if (!humanSession.csrf || ['GET', 'HEAD', 'OPTIONS'].includes((options.method ?? 'GET').toUpperCase())) return options
  const headers = new Headers(options.headers)
  headers.set('X-CSRF-Token', humanSession.csrf)
  return { ...options, headers }
}

export function expireHumanSession() {
  if (humanSession.enabled) Object.assign(humanSession, { authenticated: false, csrf: '', error: 'Your session ended. Sign in again to continue.' })
}

export async function signOut() {
  await authRequest('/api/auth/logout', withSessionHeaders({ method: 'POST' }))
  Object.assign(humanSession, { authenticated: false, csrf: '', error: '' })
}
