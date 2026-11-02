/** Private QR handoff; URL fragments never enter HTTP requests or Referer. */
import { decode64, encode64 } from './crypto'
export interface PairingHandoff { recovery: string; email: string }
const prefix = '#pair='
function validate(value: unknown): PairingHandoff {
  const data = value as PairingHandoff
  if (!data || typeof data.recovery !== 'string' || !/^ats1\.[0-9a-f-]{36}\.[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$/.test(data.recovery)
    || typeof data.email !== 'string' || data.email.length > 254 || !/^[^\s@]+@[^\s@]+$/.test(data.email)) throw new Error('Invalid phone pairing code. Generate a new QR on desktop.')
  return { recovery: data.recovery, email: data.email }
}
export function publicPhoneUrl(value: string) {
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) return ''
    return url.href
  } catch { return '' }
}
export function pairingUrl(origin: string, handoff: PairingHandoff) {
  const url = publicPhoneUrl(origin)
  if (!url) throw new Error('Configure a public HTTPS phone address without credentials or parameters')
  return url + prefix + encode64(new TextEncoder().encode(JSON.stringify(validate(handoff))))
}
export function readPairingFragment(fragment: string): PairingHandoff | undefined {
  if (!fragment.startsWith(prefix)) return undefined
  if (fragment.length > 1024) throw new Error('Invalid phone pairing code. Generate a new QR on desktop.')
  try { return validate(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(decode64(fragment.slice(prefix.length))))) }
  catch { throw new Error('Invalid phone pairing code. Generate a new QR on desktop.') }
}
/** Strip secrets before loading OAuth/other optional scripts; never persist them. */
export function consumePairing(location: Pick<Location, 'hash' | 'pathname' | 'search'>, history: Pick<History, 'replaceState'>) {
  const fragment = location.hash
  if (!fragment.startsWith(prefix)) return undefined
  history.replaceState(null, '', location.pathname + location.search)
  return readPairingFragment(fragment)
}
