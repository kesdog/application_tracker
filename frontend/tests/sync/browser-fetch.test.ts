// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { DRIVE_SCOPE, GoogleAuthorization, type Authorization } from '../../src/phone/core/auth'
import { GoogleDriveTransport } from '../../src/phone/core/drive'
afterEach(() => vi.unstubAllGlobals())
it('uses browser-compatible fetch receivers in the production auth and Drive defaults', async () => {
  const receivers: unknown[] = []
  // Browser fetch rejects an arbitrary class instance as its receiver. Node's
  // permissive fetch and injected arrow mocks otherwise conceal this regression.
  vi.stubGlobal('fetch', function (this: unknown, input: RequestInfo | URL) {
    receivers.push(this)
    if (this !== undefined && this !== window) throw new TypeError('Illegal invocation')
    return Promise.resolve(String(input).includes('/userinfo')
      ? Response.json({ sub: 'synthetic-subject', email: 'synthetic@example.invalid', email_verified: true })
      : Response.json({ startPageToken: 'synthetic-cursor' }))
  })
  const auth = new GoogleAuthorization('synthetic.apps.googleusercontent.com', async () => ({ access_token: 'synthetic', expires_in: 100, scope: DRIVE_SCOPE }))
  await auth.connect()
  const drive = new GoogleDriveTransport(auth as Authorization)
  expect(await drive.startCursor()).toBe('synthetic-cursor'); expect(receivers).toHaveLength(2)
})
