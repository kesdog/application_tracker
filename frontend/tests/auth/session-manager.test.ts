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

it('ignores a delayed authenticated check after confirmed logout', async () => {
  const pending = delayed()
  const sessions = new BrowserSessionManager()
  sessions.accept(authenticated)
  const request = vi.fn().mockReturnValueOnce(pending.response).mockResolvedValueOnce(reply({ authenticated: false }))
  const login = new WorkspaceLoginClient(sessions, request)
  const checking = login.check()
  await login.signOut()
  pending.resolve(reply(authenticated))
  await checking
  expect(sessions.state.authenticated).toBe(false)
  expect(sessions.state.csrf).toBe('')
})

it('ignores a delayed check after session expiry or a newer login', async () => {
  const pending = delayed()
  const sessions = new BrowserSessionManager()
  sessions.accept(authenticated)
  const request = vi.fn().mockReturnValueOnce(pending.response).mockResolvedValueOnce(reply({ ...authenticated, csrf_token: 'new-csrf' }))
  const login = new WorkspaceLoginClient(sessions, request)
  const checking = login.check()
  sessions.expire()
  expect(sessions.state.authenticated).toBe(false)
  await login.signIn('new password')
  pending.resolve(reply({ enabled: true, authenticated: false, csrf_token: null }))
  await checking
  expect(sessions.state.authenticated).toBe(true)
  expect(sessions.state.csrf).toBe('new-csrf')
})

it('does not claim successful logout when the server rejects it', async () => {
  const sessions = new BrowserSessionManager()
  sessions.accept(authenticated)
  const login = new WorkspaceLoginClient(sessions, vi.fn().mockResolvedValue(reply({ detail: 'Try again' }, 503)))
  await expect(login.signOut()).rejects.toThrow('Try again')
  expect(sessions.state.authenticated).toBe(true)
})


it('cannot restore an expired session from a delayed successful response', async () => {
  const pending = delayed()
  const sessions = new BrowserSessionManager()
  sessions.accept(authenticated)
  const login = new WorkspaceLoginClient(sessions, vi.fn().mockReturnValue(pending.response))
  const checking = login.check()
  sessions.expire()
  pending.resolve(reply(authenticated))
  await checking
  expect(sessions.state.authenticated).toBe(false)
  expect(sessions.state.error).toContain('session ended')
})

it('requires an explicit logout acknowledgement', async () => {
  const sessions = new BrowserSessionManager()
  sessions.accept(authenticated)
  const login = new WorkspaceLoginClient(sessions, vi.fn().mockResolvedValue(reply({})))
  await expect(login.signOut()).rejects.toThrow('Unable to confirm sign-out')
  expect(sessions.state.authenticated).toBe(true)
})
