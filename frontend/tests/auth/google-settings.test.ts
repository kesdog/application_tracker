// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import GoogleSettings from '../../src/components/settings/GoogleSettings.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getConnections: vi.fn(), startGoogle: vi.fn(), disconnectGoogle: vi.fn(), testGoogleDrive: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const disconnected: api.GoogleConnection = { configured: true, status: 'DISCONNECTED', email: null, capabilities: { drive: false, gmail_read: false, gmail_drafts: false }, updated_at: null, verified_at: null, message: null }
const connected: api.GoogleConnection = { ...disconnected, status: 'PARTIAL', email: 'owner@example.com', capabilities: { drive: true, gmail_read: true, gmail_drafts: false } }
const button = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.getConnections).mockResolvedValue({ google: disconnected }) })

it('requires explicit capabilities, retains choices on failure and exposes no second agent identity', async () => {
  const wrapper = mount(GoogleSettings, { global })
  await flushPromises()
  expect(button(wrapper, 'Connect Google').attributes('disabled')).toBeDefined()
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
  expect(wrapper.findAll('input[type=checkbox]').map(input => (input.element as HTMLInputElement).checked)).toEqual([true, true, false])
  vi.mocked(api.disconnectGoogle).mockRejectedValueOnce(new Error('Credential store locked')).mockResolvedValue(disconnected)
  await button(wrapper, 'Disconnect Google').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('owner@example.com')
  await button(wrapper, 'Disconnect Google').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('No account connected')
  expect(wrapper.text()).toContain('Local records and agent access are available')
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
  expect(wrapper.get('[role=status]').text()).toContain('Verified and removed')
})

it('keeps connection disabled when Google is not configured', async () => {
  vi.mocked(api.getConnections).mockResolvedValue({ google: { ...disconnected, configured: false } })
  const wrapper = mount(GoogleSettings, { global }); await flushPromises()
  expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('GOOGLE_CLIENT_ID')
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
