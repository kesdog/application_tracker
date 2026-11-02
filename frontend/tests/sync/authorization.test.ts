import { expect, it, vi } from 'vitest'
import { GoogleAuthorization, DRIVE_SCOPE, type Authorization } from '../../src/phone/core/auth'
import { GoogleDriveTransport, ProviderError } from '../../src/phone/core/drive'

function credentials() {
  let valid = true
  const auth: Authorization = {
    connect: async () => ({ subject: 'verified-subject', email: 'synthetic@example.invalid' }),
    identity: () => valid ? { subject: 'verified-subject', email: 'synthetic@example.invalid' } : undefined,
    token: () => { if (!valid) throw new Error('not authorized'); return 'synthetic-access-token' },
    clear: vi.fn(() => { valid = false }), invalidate: vi.fn(() => auth.clear()),
  }
  return auth
}

it('keeps tokens in the injected session and validates identity with Google before enabling sync', async () => {
  let now = 1000
  const request = vi.fn(async () => ({ access_token: 'synthetic-token', expires_in: 100, scope: 'openid email ' + DRIVE_SCOPE }))
  const http = vi.fn(async () => Response.json({ sub: 'verified-subject', email: 'synthetic@example.invalid', email_verified: true }))
  const auth = new GoogleAuthorization('phone.apps.googleusercontent.com', request, http, () => now)
  expect(await auth.connect()).toEqual({ subject: 'verified-subject', email: 'synthetic@example.invalid' })
  expect(auth.token()).toBe('synthetic-token')
  expect(http).toHaveBeenCalledWith('https://openidconnect.googleapis.com/v1/userinfo', expect.objectContaining({ credentials: 'omit', cache: 'no-store', redirect: 'error' }))
  now += 71_000
  expect(() => auth.token()).toThrow('Reconnect Google'); expect(auth.identity()).toBeUndefined()
})

it('rejects a missing Drive grant or an unverified Google identity', async () => {
  const denied = new GoogleAuthorization('phone.apps.googleusercontent.com', async () => ({ access_token: 'synthetic', expires_in: 100, scope: 'openid email' }))
  await expect(denied.connect()).rejects.toThrow('did not grant Drive')
  const unverified = new GoogleAuthorization('phone.apps.googleusercontent.com', async () => ({ access_token: 'synthetic', expires_in: 100, scope: DRIVE_SCOPE }), async () => Response.json({ sub: 'subject', email: 'synthetic@example.invalid', email_verified: false }))
  await expect(unverified.connect()).rejects.toThrow('verified identity'); expect(() => unverified.token()).toThrow('Reconnect')
})

it('reuses the authorization class for another Google capability without requesting Drive', async () => {
  const permission = 'https://www.googleapis.com/auth/calendar.readonly'
  const request = vi.fn(async () => ({ access_token: 'synthetic-other-provider-token', expires_in: 100, scope: permission }))
  const auth = new GoogleAuthorization('another.apps.googleusercontent.com', request,
    async () => Response.json({ sub: 'verified-subject', email: 'synthetic@example.invalid', email_verified: true }), Date.now, [permission])
  await auth.connect()
  expect(request).toHaveBeenCalledWith('another.apps.googleusercontent.com', [permission]); expect(auth.token()).toBe('synthetic-other-provider-token')
})

it('passes explicit sign-in recovery options to the injected requester while verifying identity', async () => {
  const request = vi.fn(async () => ({ access_token: 'synthetic-resumed-token', expires_in: 100, scope: DRIVE_SCOPE }))
  const auth = new GoogleAuthorization('phone.apps.googleusercontent.com', request, async () => Response.json({ sub: 'verified-subject', email: 'synthetic@example.invalid', email_verified: true }))
  await auth.connect({ prompt: '' })
  expect(request).toHaveBeenCalledWith('phone.apps.googleusercontent.com', [DRIVE_SCOPE], { prompt: '' }); expect(auth.identity()!.subject).toBe('verified-subject')
})

it('does not restore a cancelled authorization and does not invalidate a newer token on a stale rejection', async () => {
  let complete!: (value: any) => void
  const auth = new GoogleAuthorization('phone.apps.googleusercontent.com', () => new Promise(resolve => { complete = resolve }), async () => Response.json({ sub: 'subject', email: 'synthetic@example.invalid', email_verified: true }))
  const connecting = auth.connect(); auth.clear(); complete({ access_token: 'old', expires_in: 100, scope: DRIVE_SCOPE })
  await expect(connecting).rejects.toThrow('cancelled'); expect(auth.identity()).toBeUndefined()
  const current = new GoogleAuthorization('phone.apps.googleusercontent.com', async () => ({ access_token: 'new', expires_in: 100, scope: DRIVE_SCOPE }), async () => Response.json({ sub: 'subject', email: 'synthetic@example.invalid', email_verified: true }))
  await current.connect(); current.invalidate('old'); expect(current.token()).toBe('new')
})

it.each(['timeout', 'cancel'])('bounds and aborts identity verification on %s', async mode => {
  let started!: () => void, signal: AbortSignal | undefined
  const begun = new Promise<void>(resolve => { started = resolve })
  const http: typeof fetch = async (_url, init) => new Promise((_resolve, reject) => {
    signal = init!.signal!; started()
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })
  const auth = new GoogleAuthorization('phone.apps.googleusercontent.com', async () => ({ access_token: 'synthetic', expires_in: 100, scope: DRIVE_SCOPE }), http, Date.now, [DRIVE_SCOPE], 20)
  const rejected = expect(auth.connect()).rejects.toThrow(mode === 'timeout' ? 'timed out' : 'cancelled')
  await begun
  if (mode === 'cancel') auth.clear()
  await rejected; expect(signal!.aborted).toBe(true); expect(auth.identity()).toBeUndefined(); expect(() => auth.token()).toThrow('Reconnect')
})

it.each([
  [403, 'userRateLimitExceeded', 'rate_limit'], [403, 'storageQuotaExceeded', 'storage_full'],
  [403, 'accessNotConfigured', 'setup_required'], [403, 'SERVICE_DISABLED', 'setup_required'], [503, 'backendError', 'unavailable'],
])('preserves credentials for %s/%s and hides provider bodies', async (status, reason, kind) => {
  const auth = credentials(), http = vi.fn(async () => Response.json({ error: { details: [{ reason }], message: 'private-provider-body' } }, { status: Number(status), headers: { 'Retry-After': '9'.repeat(60) } }))
  const drive = new GoogleDriveTransport(auth, http)
  const error = await drive.startCursor().catch(value => value) as ProviderError
  expect(error.kind).toBe(kind); expect(error.message).not.toContain('private-provider-body'); expect(error.retryAfter).toBeLessThanOrEqual(3600)
  expect(auth.clear).not.toHaveBeenCalled(); expect(auth.identity()).toBeDefined()
})

it('invalidates only actual authorization loss and never retries an uncertain upload', async () => {
  const auth = credentials(), unauthorized = new GoogleDriveTransport(auth, async () => new Response('', { status: 401 }))
  await expect(unauthorized.startCursor()).rejects.toThrow('Reconnect Google'); expect(auth.clear).toHaveBeenCalledOnce()
  const write = vi.fn(async () => { throw new TypeError('synthetic upload timed out') }), drive = new GoogleDriveTransport(credentials(), write)
  await expect(drive.upload(crypto.randomUUID(), new Uint8Array([1]))).rejects.toThrow('unavailable'); expect(write).toHaveBeenCalledOnce()
})

it('paginates discovery and uploads immutable multipart data without cookies or redirects', async () => {
  const auth = credentials(), calls: { url: URL; init: RequestInit }[] = []
  const http: typeof fetch = async (input, init = {}) => {
    const url = new URL(String(input)); calls.push({ url, init })
    if (init.method === 'POST') {
      expect(init.body).toBeInstanceOf(Blob)
      const body = await (init.body as Blob).text(); expect(body).toContain('appDataFolder'); expect(body).toContain('tracker-sync-v1-')
      return Response.json({ id: 'uploaded' })
    }
    return Response.json(url.searchParams.has('pageToken') ? { files: [{ id: 'second', name: 'tracker-sync-v1-second' }] } : { files: [{ id: 'first', name: 'tracker-sync-v1-first' }, { id: 'other', name: 'unrelated' }], nextPageToken: 'next' })
  }
  const drive = new GoogleDriveTransport(auth, http)
  expect((await drive.list()).map(file => file.id)).toEqual(['first', 'second'])
  expect(await drive.upload(crypto.randomUUID(), new Uint8Array([1, 2]))).toBe('uploaded')
  for (const call of calls) {
    expect(call.url.origin).toBe('https://www.googleapis.com'); expect(call.init.credentials).toBe('omit'); expect(call.init.redirect).toBe('error'); expect(call.init.cache).toBe('no-store')
    expect((call.init.headers as Record<string, string>).Authorization).toBe('Bearer synthetic-access-token')
  }
})

it('rejects repeated discovery page tokens instead of looping forever', async () => {
  const http = vi.fn(async () => Response.json({ nextPageToken: 'same', files: [] }))
  await expect(new GoogleDriveTransport(credentials(), http).list()).rejects.toThrow('repeated page')
  expect(http).toHaveBeenCalledTimes(2)
})
