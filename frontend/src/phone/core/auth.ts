/** OAuth access-token lifetime and verified identity are independent of sync/storage. */
import { requireValue } from './protocol'
export const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.appdata'
export interface Identity { subject: string; email: string }
export interface Authorization {
  connect(options?: TokenRequestOptions): Promise<Identity>; identity(): Identity | undefined; token(): string; clear(): void; invalidate(token: string): void
}
export interface TokenResponse { access_token?: string; expires_in?: number; scope?: string; error?: string }
export interface TokenRequestOptions { prompt?: '' | 'select_account'; loginHint?: string }
export type TokenRequester = (clientId: string, scopes: readonly string[], options?: TokenRequestOptions) => Promise<TokenResponse>
export class GoogleAuthorization implements Authorization {
  private accessToken = ''; private expires = 0; private owner?: Identity; private generation = 0; private identityRequest?: AbortController
  constructor(private readonly clientId: string, private readonly requestToken: TokenRequester = googleToken,
    private readonly http: typeof fetch = (input, init) => fetch(input, init), private readonly clock = Date.now, private readonly requiredScopes: readonly string[] = [DRIVE_SCOPE], private readonly identityTimeoutMs = 15_000) {}
  async connect(options?: TokenRequestOptions): Promise<Identity> {
    requireValue(/^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(this.clientId), 'Enter the phone Web OAuth public client ID')
    this.identityRequest?.abort()
    const generation = ++this.generation; this.accessToken = ''; this.owner = undefined; this.expires = 0
    const response = options ? await this.requestToken(this.clientId, this.requiredScopes, options) : await this.requestToken(this.clientId, this.requiredScopes)
    requireValue(generation === this.generation, 'Google authorization was cancelled or expired')
    requireValue(!response.error && response.access_token && this.requiredScopes.every(scope => response.scope?.split(' ').includes(scope)), this.requiredScopes.includes(DRIVE_SCOPE) ? 'Google did not grant Drive app-data access. Reconnect and allow Drive.' : 'Google did not grant the required permissions.')
    const expires = this.clock() + Math.max(0, Number(response.expires_in ?? 0) - 30) * 1000
    const controller = new AbortController(); this.identityRequest = controller
    const timer = setTimeout(() => controller.abort(), this.identityTimeoutMs)
    try {
      const userResponse = await this.http('https://openidconnect.googleapis.com/v1/userinfo', { headers: { Authorization: 'Bearer ' + response.access_token }, credentials: 'omit', cache: 'no-store', redirect: 'error', signal: controller.signal })
      requireValue(userResponse.ok, 'Google identity verification failed')
      const user = await userResponse.json()
      requireValue(typeof user.sub === 'string' && user.sub.length > 0 && user.email_verified === true && typeof user.email === 'string', 'Google did not return a verified identity')
      requireValue(generation === this.generation && expires > this.clock(), 'Google authorization was cancelled or expired')
      this.owner = { subject: user.sub, email: user.email }; this.accessToken = response.access_token; this.expires = expires
      return { ...this.owner }
    } catch (error) {
      if (controller.signal.aborted) throw new Error(generation !== this.generation ? 'Google authorization was cancelled.' : 'Google identity verification timed out. Try again.')
      throw error
    } finally { clearTimeout(timer); if (this.identityRequest === controller) this.identityRequest = undefined }
  }
  identity() { return this.owner && { ...this.owner } }
  token() { if (this.expires <= this.clock()) this.clear(); requireValue(this.accessToken, 'Reconnect Google to sync. Offline edits are saved.'); return this.accessToken }
  clear() { this.generation++; this.identityRequest?.abort(); this.identityRequest = undefined; this.accessToken = ''; this.owner = undefined; this.expires = 0 }
  invalidate(token: string) { if (token === this.accessToken) this.clear() }
}
interface TokenClient { requestAccessToken(options: { prompt: string; login_hint?: string }): void }
interface OAuthAPI { initTokenClient(options: { client_id: string; scope: string; include_granted_scopes: boolean; callback: (response: TokenResponse) => void; error_callback: () => void }): TokenClient }
type GoogleWindow = Window & { google?: { accounts?: { oauth2?: OAuthAPI } } }
let loading: Promise<OAuthAPI> | undefined
export function loadGoogleOAuth(): Promise<OAuthAPI> {
  const api = (window as GoogleWindow).google?.accounts?.oauth2
  if (api) return Promise.resolve(api)
  return loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = 'https://accounts.google.com/gsi/client'; script.async = true
    const timer = window.setTimeout(failed, 12_000)
    function failed() { clearTimeout(timer); script.remove(); loading = undefined; reject(new Error('Google could not load. Reconnect to the internet and try again.')) }
    script.onerror = failed; script.onload = () => { const ready = (window as GoogleWindow).google?.accounts?.oauth2; if (ready) { clearTimeout(timer); resolve(ready) } else failed() }; document.head.append(script)
  })
}
/** Preload the script on mount; call this from a user gesture to avoid blocked popups. */
export async function googleToken(clientId: string, scopes: readonly string[] = [DRIVE_SCOPE], options: TokenRequestOptions = {}): Promise<TokenResponse> {
  const api = await loadGoogleOAuth()
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('Google authorization timed out. Try again.')), 120_000)
    // Existing-session retries leave authentication and consent to Google;
    // the verified identity and replica account checks still run afterward.
    const prompt = options.prompt ?? 'select_account'
    api.initTokenClient({ client_id: clientId, scope: ['openid', 'email', ...scopes].join(' '), include_granted_scopes: false,
      callback: response => { clearTimeout(timer); resolve(response) }, error_callback: () => { clearTimeout(timer); reject(new Error('Google authorization was cancelled or the popup was blocked.')) },
    }).requestAccessToken({ prompt, ...(options.loginHint?.trim() ? { login_hint: options.loginHint.trim() } : {}) })
  })
}
