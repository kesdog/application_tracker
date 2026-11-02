// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { DRIVE_SCOPE, googleToken, type TokenRequestOptions } from '../../src/phone/core/auth'
afterEach(() => vi.unstubAllGlobals())
it.each([undefined, { prompt: '' }, { prompt: '', loginHint: 'synthetic@example.invalid' }] as (TokenRequestOptions | undefined)[])('keeps the requested scopes when starting an OAuth popup with %j', async options => {
  const request = vi.fn(), init = vi.fn((config: any) => ({ requestAccessToken: (override: unknown) => { request(override); config.callback({ access_token: 'synthetic-popup-token', expires_in: 100, scope: DRIVE_SCOPE }) } }))
  vi.stubGlobal('google', { accounts: { oauth2: { initTokenClient: init } } })
  const response = await googleToken('synthetic.apps.googleusercontent.com', [DRIVE_SCOPE], options)
  expect(request).toHaveBeenCalledWith({ prompt: options?.prompt ?? 'select_account', ...(options?.loginHint ? { login_hint: options.loginHint } : {}) }); expect(init).toHaveBeenCalledWith(expect.objectContaining({ scope: 'openid email ' + DRIVE_SCOPE, include_granted_scopes: false })); expect(response.access_token).toBe('synthetic-popup-token')
})
