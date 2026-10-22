import { expect, it, vi } from 'vitest'
import { BrowserSessionManager, WorkspaceLoginClient } from '../../src/auth'

const authenticated = { enabled: true, authenticated: true, csrf_token: 'current-csrf' }
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
function delayed() {
  let resolve!: (value: Response) => void
  const response = new Promise<Response>(done => { resolve = done })
  return { response, resolve }
}

it('shares one session between independently constructed login consumers', async () => {
  const sessions = new BrowserSessionManager()
  const first = new WorkspaceLoginClient(sessions, vi.fn().mockResolvedValue(reply(authenticated)))
  const second = new WorkspaceLoginClient(sessions, vi.fn().mockResolvedValue(reply({ authenticated: false })))
  await first.signIn('test password')
  expect(second.sessions.state.authenticated).toBe(true)
  await second.signOut()
  expect(first.sessions.state.authenticated).toBe(false)
  expect(first.sessions.state.csrf).toBe('')
})

it('ignores stale checks after logout, expiry and a newer login', async () => {
  for (const transition of ['logout', 'expiry', 'new login']) {
    const pending = delayed()
    const sessions = new BrowserSessionManager()
    sessions.accept(authenticated)
    const next = transition === 'logout' ? { authenticated: false } : { ...authenticated, csrf_token: 'new-csrf' }
    const request = vi.fn().mockReturnValueOnce(pending.response).mockResolvedValueOnce(reply(next))
    const login = new WorkspaceLoginClient(sessions, request)
    const checking = login.check()
    if (transition === 'logout') await login.signOut()
    else {
      sessions.expire()
      expect(sessions.state.authenticated, transition).toBe(false)
      if (transition === 'new login') await login.signIn('new password')
    }
    pending.resolve(reply(transition === 'new login' ? { enabled: true, authenticated: false, csrf_token: null } : authenticated))
    await checking
    expect(sessions.state.authenticated, transition).toBe(transition === 'new login')
    expect(sessions.state.csrf, transition).toBe(transition === 'new login' ? 'new-csrf' : '')
    if (transition === 'expiry') expect(sessions.state.error).toContain('session ended')
  }
})

it('requires a successful, explicit logout acknowledgement', async () => {
  for (const [body, status, error] of [
    [{ detail: 'Try again' }, 503, 'Try again'],
    [{}, 200, 'Unable to confirm sign-out'],
  ] as const) {
    const sessions = new BrowserSessionManager()
    sessions.accept(authenticated)
    const login = new WorkspaceLoginClient(sessions, vi.fn().mockResolvedValue(reply(body, status)))
    await expect(login.signOut()).rejects.toThrow(error)
    expect(sessions.state.authenticated, error).toBe(true)
  }
})
