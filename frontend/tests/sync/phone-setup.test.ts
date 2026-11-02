// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import PhoneSetup from '../../src/components/sync/PhoneSetup.vue'
const status = vi.hoisted(() => vi.fn())
vi.mock('../../src/googleAuth', () => ({ googleLogin: { status } }))
afterEach(() => vi.clearAllMocks())
it('offers pairing directly in Phone settings using the existing Google connection', async () => {
  status.mockResolvedValue({ capabilities: { drive: true }, email: 'synthetic@example.invalid' })
  const view = mount(PhoneSetup, { global: { stubs: { PhonePairingLink: { props: ['driveReady', 'accountEmail'], template: '<button :disabled="!driveReady">Pair phone {{ accountEmail }}</button>' } } } }); await flushPromises()
  expect(view.get('button').attributes('disabled')).toBeUndefined()
  expect(view.text()).toContain('synthetic@example.invalid'); view.unmount()
})
it('keeps pairing disabled and provides a connection link on status failure', async () => {
  status.mockRejectedValue(new Error('offline'))
  const view = mount(PhoneSetup, { global: { stubs: { PhonePairingLink: true } } }); await flushPromises()
  expect(view.get('[role=alert]').text()).toContain('Unable to check Google')
  expect(view.get('a').attributes('href')).toBe('#/settings?tab=connections'); view.unmount()
})
