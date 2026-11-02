// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import PhonePairingLink from '../../src/components/sync/PhonePairingLink.vue'
import { consumePairing, pairingUrl, publicPhoneUrl, readPairingFragment } from '../../src/phone/core/pairing'
import { fixture } from './support'
const mocks = vi.hoisted(() => ({ render: vi.fn(async (_url: string, _options?: unknown) => 'data:image/png;base64,synthetic'), prepare: vi.fn() }))
vi.mock('qrcode', () => ({ default: { toDataURL: mocks.render } }))
vi.mock('../../src/syncClient', () => ({ syncClient: { preparePhone: mocks.prepare } }))
const handoff = { recovery: fixture.crypto.recovery, email: 'synthetic@example.invalid' }
afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks(); vi.useRealTimers() })
it('prepares and displays a private handoff only after the explicit button; hides it on departure', async () => {
  vi.stubEnv('VITE_PHONE_URL', 'https://phone.example.invalid/phone/')
  mocks.prepare.mockResolvedValue({ recovery_export: handoff.recovery, status: { initialized: true } })
  const view = mount(PhonePairingLink, { props: { driveReady: true, accountEmail: handoff.email } }); await flushPromises()
  expect(mocks.prepare).not.toHaveBeenCalled(); expect(mocks.render).not.toHaveBeenCalled()
  await view.get('button').trigger('click'); await flushPromises()
  const url = new URL(mocks.render.mock.calls[0]![0] as string)
  expect(url.search).toBe(''); expect(readPairingFragment(url.hash)).toEqual(handoff)
  expect(view.text()).toContain('recovery key'); expect(view.emitted('prepared')).toHaveLength(1)
  window.dispatchEvent(new Event('pagehide')); expect(view.find('img').exists()).toBe(true)
  await flushPromises(); expect(view.find('img').exists()).toBe(false); view.unmount()
})
it('scrubs the fragment from history before consuming the private handoff', () => {
  const url = new URL(pairingUrl('https://phone.example.invalid/phone/', handoff)), replaceState = vi.fn()
  expect(consumePairing(url, { replaceState })).toEqual(handoff)
  expect(replaceState).toHaveBeenCalledWith(null, '', '/phone/')
  expect(() => consumePairing({ hash: '#pair=broken', pathname: '/phone/', search: '' }, { replaceState })).toThrow('Invalid phone pairing')
  expect(replaceState).toHaveBeenCalledTimes(2)
})
it.each(['http://phone.example.invalid/phone/', 'https://phone.example.invalid/phone/#ats1.secret', 'https://phone.example.invalid/phone/?key=secret', 'https://name:secret@phone.example.invalid/phone/'])('rejects unsafe pairing destinations: %s', url => {
  expect(publicPhoneUrl(url)).toBe(''); expect(() => pairingUrl(url, handoff)).toThrow()
})
it('blocks setup without Drive, and surfaces bootstrap errors without showing a QR', async () => {
  vi.stubEnv('VITE_PHONE_URL', 'https://phone.example.invalid/phone/')
  const view = mount(PhonePairingLink, { props: { driveReady: false, accountEmail: handoff.email } }); await flushPromises()
  expect(view.get('button').attributes('disabled')).toBeDefined()
  await view.setProps({ driveReady: true }); mocks.prepare.mockRejectedValue(new Error('Drive is offline'))
  await view.get('button').trigger('click'); await flushPromises()
  expect(view.text()).toContain('Drive is offline'); expect(view.find('img').exists()).toBe(false); view.unmount()
})
