// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import ProviderSignIn from '../../src/components/auth/ProviderSignIn.vue'
import { workspaceLogin } from '../../src/auth'
import { identityRequest, loadGoogleIdentity, type GoogleIdentity } from '../../src/googleIdentity'

vi.mock('../../src/googleIdentity', () => ({ identityRequest: vi.fn(), loadGoogleIdentity: vi.fn() }))
vi.mock('../../src/auth', () => ({ workspaceLogin: { signInGoogle: vi.fn() } }))
enableAutoUnmount(afterEach)
let identity: GoogleIdentity
let disconnect = vi.fn(() => {})
beforeEach(() => {
  vi.resetAllMocks()
  disconnect = vi.fn(() => {})
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() { disconnect() } })
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(340)
  identity = { initialize: vi.fn(), renderButton: vi.fn() }
  vi.mocked(loadGoogleIdentity).mockResolvedValue(identity)
  vi.mocked(identityRequest).mockImplementation(async path => path === '/api/auth/providers' ? { google: { available: true, client_id: 'test-client' } } : { state: 'browser-state', nonce: 'nonce' })
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('initializes the standard Google button and exchanges its credential without navigation', async () => {
  const wrapper = mount(ProviderSignIn)
  await flushPromises()
  expect(identity.initialize).toHaveBeenCalledWith(expect.objectContaining({ client_id: 'test-client', nonce: 'nonce', auto_select: false, ux_mode: 'popup' }))
  expect(identity.renderButton).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ type: 'standard', size: 'large', text: 'continue_with', width: 309 }))
  const options = vi.mocked(identity.initialize).mock.calls[0]![0]
  options.callback({ credential: 'google-signed-token' })
  await flushPromises()
  expect(workspaceLogin.signInGoogle).toHaveBeenCalledWith('google-signed-token', 'browser-state')
  expect(wrapper.emitted('busy')).toEqual([[true], [false]])
  wrapper.unmount()
  expect(disconnect).toHaveBeenCalled()
  options.callback({ credential: 'stale-token' })
  expect(workspaceLogin.signInGoogle).toHaveBeenCalledTimes(1)
})

it('explains unavailable providers without loading Google or claiming an AI account login', async () => {
  vi.mocked(identityRequest).mockResolvedValue({ google: { available: false, client_id: null } })
  const wrapper = mount(ProviderSignIn)
  await flushPromises()
  expect(loadGoogleIdentity).not.toHaveBeenCalled()
  for (const [label, panel] of [['Continue with Google', 'google-help'], ['Connect Claude', 'claude-help'], ['Connect ChatGPT', 'chatgpt-help']]) {
    const button = wrapper.findAll('button').find(button => button.text().includes(label!))!
    await button.trigger('click')
    expect(button.attributes('aria-expanded')).toBe('true')
    expect(button.attributes('aria-controls')).toBe(panel)
    expect(wrapper.get('#' + panel).text()).toContain(label!.includes('Google') ? 'workspace password' : label!.includes('Claude') ? 'does not sign you in' : 'local installation')
  }
  expect(wrapper.find('input[type=password]').exists()).toBe(false)
  expect(workspaceLogin.signInGoogle).not.toHaveBeenCalled()
})

it('shows an SDK failure and permits a new attempt', async () => {
  vi.mocked(loadGoogleIdentity).mockRejectedValueOnce(new Error('Google content blocked'))
  const wrapper = mount(ProviderSignIn)
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('Google content blocked')
  await wrapper.findAll('button').find(button => button.text() === 'Retry Google sign-in')!.trigger('click')
  await flushPromises()
  expect(identity.initialize).toHaveBeenCalledTimes(1)
  expect(wrapper.find('[role=alert]').exists()).toBe(false)
})

it('keeps failed sign-in visible and requires a fresh nonce before retrying', async () => {
  vi.mocked(workspaceLogin.signInGoogle).mockRejectedValueOnce(new Error('Use an allowed account'))
  const wrapper = mount(ProviderSignIn)
  await flushPromises()
  vi.mocked(identity.initialize).mock.calls[0]![0].callback({ credential: 'wrong-account' })
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('Use an allowed account')
  await wrapper.findAll('button').find(button => button.text() === 'Retry Google sign-in')!.trigger('click')
  await flushPromises()
  expect(identityRequest).toHaveBeenCalledWith('/api/auth/google/start', true)
  expect(identity.initialize).toHaveBeenCalledTimes(2)
})

it('ignores a delayed SDK response after unmount and blocks Google while password login is busy', async () => {
  const wrapper = mount(ProviderSignIn, { props: { disabled: true } })
  await flushPromises()
  vi.mocked(identity.initialize).mock.calls[0]![0].callback({ credential: 'token' })
  expect(workspaceLogin.signInGoogle).not.toHaveBeenCalled()
  expect(wrapper.get('.google-target').attributes('inert')).toBeDefined()
  wrapper.unmount()
  let resolve!: (identity: GoogleIdentity) => void
  vi.mocked(loadGoogleIdentity).mockReturnValueOnce(new Promise(done => { resolve = done }))
  const delayed = mount(ProviderSignIn)
  await flushPromises()
  delayed.unmount()
  const count = vi.mocked(identity.initialize).mock.calls.length
  resolve(identity)
  await flushPromises()
  expect(identity.initialize).toHaveBeenCalledTimes(count)
})
