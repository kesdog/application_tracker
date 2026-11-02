import { t } from './i18n'
export interface GoogleIdentity {
  initialize(options: { client_id: string; nonce: string; callback: (response: { credential: string }) => void; auto_select: boolean; ux_mode: 'popup' }): void
  renderButton(element: HTMLElement, options: { type: 'standard'; theme: 'outline' | 'filled_black'; size: 'large'; text: 'continue_with'; width: number }): void
}
declare global { interface Window { google?: { accounts?: { id?: GoogleIdentity } } } }

let loading: Promise<GoogleIdentity> | undefined
export function loadGoogleIdentity(): Promise<GoogleIdentity> {
  const identity = window.google?.accounts?.id
  if (identity) return Promise.resolve(identity)
  if (loading) return loading
  loading = new Promise<GoogleIdentity>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    const timer = window.setTimeout(() => fail(), 12000)
    function fail() {
      window.clearTimeout(timer)
      script.remove()
      loading = undefined
      reject(new Error(t("Google sign-in could not load. Check your connection or content blocker, then try again.")))
    }
    script.onerror = fail
    script.onload = () => {
      window.clearTimeout(timer)
      const ready = window.google?.accounts?.id
      if (ready) resolve(ready)
      else fail()
    }
    document.head.append(script)
  })
  return loading
}

export async function identityRequest<T>(path: string, post = false): Promise<T> {
  const response = await fetch(path, { method: post ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(8000), ...(post ? { headers: { 'Content-Type': 'application/json' }, body: '{}' } : {}) })
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : t("Unable to prepare Google sign-in. Try again."))
  return body
}
