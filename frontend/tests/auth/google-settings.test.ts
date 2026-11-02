// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import GoogleSettings from '../../src/components/settings/GoogleSettings.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getConnections: vi.fn(), getGoogleClientSetup: vi.fn(), startGoogle: vi.fn(), disconnectGoogle: vi.fn(), testGoogleDrive: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const disconnected: api.GoogleConnection = { configured: true, status: 'DISCONNECTED', email: null, capabilities: { drive: false, gmail_read: false, gmail_drafts: false }, updated_at: null, verified_at: null, message: null }
const connected: api.GoogleConnection = { ...disconnected, status: 'PARTIAL', email: 'owner@example.com', capabilities: { drive: true, gmail_read: true, gmail_drafts: false } }
const button = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.getConnections).mockResolvedValue({ google: disconnected }); vi.mocked(api.getGoogleClientSetup).mockResolvedValue({ configured: false, origin: 'http://127.0.0.1:8000', redirect_uri: 'http://127.0.0.1:8000/api/connections/google/callback', hosted: false }) })

it('allows identity-only connection and requests only explicitly chosen optional capabilities', async () => {
  const wrapper = mount(GoogleSettings, { global })
  await flushPromises()
  expect(wrapper.get('fieldset').element.closest('details')).toBeNull()
  expect(button(wrapper, 'Connect Google').attributes('disabled')).toBeUndefined()
  vi.mocked(api.startGoogle).mockRejectedValue(new Error('Unlock the credential store'))
  await button(wrapper, 'Connect Google').trigger('click')
  await flushPromises()
  expect(api.startGoogle).toHaveBeenCalledWith([])
  expect(wrapper.get('[role=alert]').text()).toContain('Unlock the credential store')
  await wrapper.findAll('input[type=checkbox]')[1]!.setValue(true)
  vi.mocked(api.startGoogle).mockRejectedValue(new Error('Unlock the credential store'))
  await button(wrapper, 'Connect Google').trigger('click')
  await flushPromises()
  expect(api.startGoogle).toHaveBeenCalledWith(['gmail_read'])
  expect(wrapper.get('[role=alert]').text()).toContain('Unlock the credential store')
  expect((wrapper.findAll('input[type=checkbox]')[1]!.element as HTMLInputElement).checked).toBe(true)
  expect(wrapper.text()).toContain('Nothing is sent')
})

it('shows partial capabilities and retains the connected identity when disconnect fails', async () => {
  vi.mocked(api.getConnections).mockResolvedValue({ google: connected })
  const wrapper = mount(GoogleSettings, { global })
  await flushPromises()
  expect(wrapper.text()).toContain('owner@example.com')
  expect(wrapper.get('[aria-label="Google account"] [role=status]').text()).toBe('Connected · owner@example.com')
  expect(wrapper.get('.provider-buttons').element.children[0]!.textContent).toContain('Connect ChatGPT')
  expect(wrapper.get('.provider-buttons').element.children[1]!.textContent).toContain('Connect Claude')
  expect(wrapper.get('.provider-buttons').element.children[2]!.textContent).toContain('Connected · owner@example.com')
  expect(wrapper.findAll('input[type=checkbox]').map(input => (input.element as HTMLInputElement).checked)).toEqual([true, true, false])
  vi.mocked(api.disconnectGoogle).mockRejectedValueOnce(new Error('Credential store locked')).mockResolvedValue(disconnected)
  await button(wrapper, 'Log out').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('owner@example.com')
  await button(wrapper, 'Log out').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('No account connected')
  expect(wrapper.text()).toContain('Local records and agent access are available')
  expect(wrapper.get('.provider-buttons').element.children[0]!.textContent).toContain('Connect Google')
  expect(wrapper.find('[aria-label="Google account"]').exists()).toBe(false)
})

it('clears the user recovery key after failed and successful Drive tests', async () => {
  vi.mocked(api.getConnections).mockResolvedValue({ google: connected })
  const wrapper = mount(GoogleSettings, { global })
  await flushPromises()
  const input = wrapper.get('input[type=password]')
  await input.setValue('a'.repeat(43))
  vi.mocked(api.testGoogleDrive).mockRejectedValueOnce(new Error('Google offline'))
  await button(wrapper, 'Test encrypted app data').trigger('click'); await flushPromises()
  expect((input.element as HTMLInputElement).value).toBe('')
  expect(wrapper.text()).toContain('Phone sync is not enabled')
  await input.setValue('b'.repeat(43))
  vi.mocked(api.testGoogleDrive).mockResolvedValue({ verified: true, deleted: true, message: 'Verified and removed' })
  await button(wrapper, 'Test encrypted app data').trigger('click'); await flushPromises()
  expect((input.element as HTMLInputElement).value).toBe('')
  expect(wrapper.findAll('[role=status]').map(item => item.text())).toContain('Verified and removed')
})

it.each(['RECONNECT_REQUIRED', 'CREDENTIALS_UNAVAILABLE'])('does not show a failed connection as connected: %s', async status => {
  vi.mocked(api.getConnections).mockResolvedValue({ google: { ...connected, status } })
  const wrapper = mount(GoogleSettings, { global }); await flushPromises()
  expect(wrapper.get('[aria-label="Google account"] [role=status]').text()).not.toContain('Connected ·')
  expect(button(wrapper, 'Reconnect Google').exists()).toBe(true)
  expect(button(wrapper, 'Log out').exists()).toBe(true)
})

it('offers all three provider buttons and opens in-app Google registration instead of a backend error', async () => {
  vi.mocked(api.getConnections).mockResolvedValue({ google: { ...disconnected, configured: false } })
  const wrapper = mount(GoogleSettings, { global }); await flushPromises()
  expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
  expect(button(wrapper, 'Connect Google').exists()).toBe(true)
  expect(button(wrapper, 'Connect ChatGPT').exists()).toBe(true)
  expect(button(wrapper, 'Connect Claude').exists()).toBe(true)
  await button(wrapper, 'Connect Google').trigger('click'); await flushPromises()
  expect(wrapper.findComponent({ name: 'GoogleSetup' }).exists()).toBe(true)
  expect(wrapper.text()).not.toContain('GOOGLE_CLIENT_ID')
  expect(api.startGoogle).not.toHaveBeenCalled()
})

it('opens the chosen agent connection directly', async () => {
  const wrapper = mount(GoogleSettings, { global }); await flushPromises()
  await button(wrapper, 'Connect ChatGPT').trigger('click')
  expect(window.location.hash).toBe('#/settings?tab=agent&provider=chatgpt')
  await button(wrapper, 'Connect Claude').trigger('click')
  expect(window.location.hash).toBe('#/settings?tab=agent&provider=claude')
})


it('rejects an unexpected authorization destination before navigating', async () => {
  const wrapper = mount(GoogleSettings, { global })
  await flushPromises()
  await wrapper.findAll('input[type=checkbox]')[1]!.setValue(true)
  vi.mocked(api.startGoogle).mockResolvedValue({ authorization_url: 'https://attacker.example/authorize', expires_in: 600 })
  await button(wrapper, 'Connect Google').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('Invalid Google authorization address')
})
