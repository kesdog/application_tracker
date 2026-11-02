// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import GoogleSetup from '../../src/components/settings/GoogleSetup.vue'
import { getGoogleClientSetup, saveGoogleClientSetup } from '../../src/api'

vi.mock('../../src/api', () => ({ getGoogleClientSetup: vi.fn(), saveGoogleClientSetup: vi.fn() }))
enableAutoUnmount(afterEach)
const setup = { configured: false, origin: 'http://127.0.0.1:8000', redirect_uri: 'http://127.0.0.1:8000/api/connections/google/callback', hosted: false }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(getGoogleClientSetup).mockResolvedValue(setup); vi.mocked(saveGoogleClientSetup).mockResolvedValue({ ...setup, configured: true }) })

async function importFile(wrapper: ReturnType<typeof mount>, body: unknown) {
  const file = new File(['fixture'], 'client.json', { type: 'application/json' })
  Object.defineProperty(file, 'text', { value: async () => typeof body === 'string' ? body : JSON.stringify(body) })
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change')
  await flushPromises()
}

it('shows exact registration addresses and imports the Google download without exposing its secret', async () => {
  const wrapper = mount(GoogleSetup); await flushPromises()
  expect(wrapper.text()).toContain(setup.origin)
  expect(wrapper.text()).toContain(setup.redirect_uri)
  expect(wrapper.text()).not.toContain('GOOGLE_CLIENT_ID')
  await importFile(wrapper, { web: { client_id: '123-fixture.apps.googleusercontent.com', client_secret: 'fixture-private-secret' } })
  expect(saveGoogleClientSetup).toHaveBeenCalledWith({ client_id: '123-fixture.apps.googleusercontent.com', client_secret: 'fixture-private-secret' })
  expect(wrapper.emitted('saved')).toHaveLength(1)
  expect(wrapper.text()).not.toContain('fixture-private-secret')
  expect((wrapper.get('input[type=file]').element as HTMLInputElement).value).toBe('')
})

it('imports a Desktop app client for a local installation', async () => {
  const wrapper = mount(GoogleSetup); await flushPromises()
  expect(wrapper.text()).toContain('Desktop app')
  await importFile(wrapper, { installed: { client_id: '123-desktop.apps.googleusercontent.com', client_secret: 'fixture-desktop-secret', redirect_uris: ['http://localhost'] } })
  expect(saveGoogleClientSetup).toHaveBeenCalledWith({ client_id: '123-desktop.apps.googleusercontent.com', client_secret: 'fixture-desktop-secret' })
  expect(wrapper.emitted('saved')).toHaveLength(1)
})

it.each(['not json', { type: 'service_account', private_key: 'fixture' }, { web: { client_id: 'not-google' } }])('rejects invalid registrations before sending credentials: %j', async body => {
  const wrapper = mount(GoogleSetup); await flushPromises()
  await importFile(wrapper, body)
  expect(saveGoogleClientSetup).not.toHaveBeenCalled()
  expect(wrapper.get('[role=alert]').text()).toMatch(/Google|OAuth/)
})

it('rejects desktop credentials for hosted sign-in and retains a visible vault error', async () => {
  vi.mocked(getGoogleClientSetup).mockResolvedValue({ ...setup, hosted: true })
  const wrapper = mount(GoogleSetup); await flushPromises()
  await importFile(wrapper, { installed: { client_id: '123-fixture.apps.googleusercontent.com' } })
  expect(saveGoogleClientSetup).not.toHaveBeenCalled()
  expect(wrapper.get('[role=alert]').text()).toContain('Web application')
  vi.mocked(saveGoogleClientSetup).mockRejectedValueOnce(new Error('Unlock secure storage'))
  await importFile(wrapper, { web: { client_id: '123-fixture.apps.googleusercontent.com' } })
  expect(wrapper.get('[role=alert]').text()).toContain('Unlock secure storage')
  expect(wrapper.emitted('saved')).toBeUndefined()
  expect(wrapper.get('input[type=file]').attributes('disabled')).toBeUndefined()
})
