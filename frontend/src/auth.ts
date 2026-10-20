import { reactive } from 'vue'

export interface SessionStatus { enabled: boolean; authenticated: boolean; csrf_token: string | null }

/** One in-memory session shared by the root, API client and event stream. */
export class BrowserSessionManager {
  readonly state = reactive({ enabled: false, authenticated: false, checking: true, loaded: false, csrf: '', error: '' })
  private revision = 0

  snapshot() { return this.revision }
  beginTransition() { this.state.checking = false; return ++this.revision }
  isCurrent(revision: number) { return revision === this.revision }

  accept(body: SessionStatus, revision = this.revision) {
    if (!this.isCurrent(revision)) return
    if (typeof body?.enabled !== 'boolean' || typeof body?.authenticated !== 'boolean' || (body.enabled && body.authenticated && (typeof body.csrf_token !== 'string' || !body.csrf_token))) throw new Error('Unexpected sign-in response. Try again.')
    Object.assign(this.state, { enabled: body.enabled, authenticated: body.authenticated, csrf: body.csrf_token ?? '', loaded: true, checking: false, error: '' })
  }

  withHeaders(options: RequestInit): RequestInit {
    if (!this.state.csrf || ['GET', 'HEAD', 'OPTIONS'].includes((options.method ?? 'GET').toUpperCase())) return options
    const headers = new Headers(options.headers)
    headers.set('X-CSRF-Token', this.state.csrf)
    return { ...options, headers }
  }

  expire() {
    this.beginTransition()
    if (this.state.enabled) Object.assign(this.state, { authenticated: false, csrf: '', checking: false, error: 'Your session ended. Sign in again to continue.' })
  }

  confirmSignOut(revision: number) {
    if (!this.isCurrent(revision)) return
    this.beginTransition()
    Object.assign(this.state, { authenticated: false, csrf: '', checking: false, error: '' })
  }
}

/** Auth HTTP orchestration is replaceable without changing session consumers. */
export class WorkspaceLoginClient {
  constructor(readonly sessions: BrowserSessionManager, private readonly request: typeof fetch = (input, options) => fetch(input, options)) {}

  private async authRequest(path: string, options: RequestInit = {}): Promise<SessionStatus> {
    const response = await this.request(path, { ...options, cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(8000) })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(typeof body?.detail === 'string' ? body.detail : `Sign-in request failed (${response.status})`)
    }
    return response.json()
  }

  async check() {
    const revision = this.sessions.snapshot()
    this.sessions.state.checking = true
    try { this.sessions.accept(await this.authRequest('/api/auth/session'), revision) }
    catch (error) {
      if (this.sessions.isCurrent(revision)) {
        this.sessions.state.error = error instanceof Error ? error.message : 'Unable to reach your workspace.'
        this.sessions.state.checking = false
      }
    }
  }

  async signIn(password: string) {
    const revision = this.sessions.beginTransition()
    this.sessions.accept(await this.authRequest('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) }), revision)
  }

  async signOut() {
    const revision = this.sessions.beginTransition()
    const result = await this.authRequest('/api/auth/logout', this.sessions.withHeaders({ method: 'POST' }))
    if (result?.authenticated !== false) throw new Error('Unable to confirm sign-out. Try again.')
    this.sessions.confirmSignOut(revision)
  }
}

export const browserSession = new BrowserSessionManager()
export const workspaceLogin = new WorkspaceLoginClient(browserSession)
// Compatibility exports share the same instances and state.
export const humanSession = browserSession.state
export const checkHumanSession = () => workspaceLogin.check()
export const signIn = (password: string) => workspaceLogin.signIn(password)
export const signOut = () => workspaceLogin.signOut()
export const withSessionHeaders = (options: RequestInit) => browserSession.withHeaders(options)
export const expireHumanSession = () => browserSession.expire()
