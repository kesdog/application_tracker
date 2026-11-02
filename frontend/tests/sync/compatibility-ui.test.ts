// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import PhoneCompatibility from '../../src/components/sync/PhoneCompatibility.vue'
const mocks = vi.hoisted(() => ({ load: vi.fn(), connect: vi.fn(), probe: vi.fn() }))
vi.mock('../../src/phone/core/auth', () => ({ loadGoogleOAuth: mocks.load, GoogleAuthorization: class { connect = mocks.connect; clear = vi.fn() } }))
vi.mock('../../src/phone/core/drive', () => ({ GoogleDriveTransport: class {} }))
vi.mock('../../src/phone/core/compatibility', () => ({ verifyCrossClient: mocks.probe }))
vi.mock('../../src/syncClient', () => ({ syncClient: {} }))
const views: ReturnType<typeof mount>[] = []
beforeEach(() => { vi.clearAllMocks(); mocks.load.mockResolvedValue({}); mocks.connect.mockResolvedValue({ subject: 'synthetic-subject' }); mocks.probe.mockResolvedValue(undefined) })
afterEach(() => { views.forEach(view => view.unmount()); views.length = 0 })
async function opened(props: { accountEmail?: string } = {}) {
  const view = mount(PhoneCompatibility, { props }); views.push(view)
  expect(mocks.load).not.toHaveBeenCalled()
  const details = view.find('details'); (details.element as HTMLDetailsElement).open = true
  await vi.waitFor(() => expect(mocks.load).toHaveBeenCalledOnce()); await flushPromises(); await view.find('input').setValue('synthetic.apps.googleusercontent.com')
  return view
}
it('loads the optional SDK only after opening, and can recover from a failed script load', async () => {
  mocks.load.mockRejectedValueOnce(new Error('Synthetic SDK load failure'))
  const view = await opened()
  expect(view.find('[role="alert"]').text()).toContain('SDK load failure'); expect(view.find('form button').attributes('disabled')).toBeDefined()
  await view.findAll('button').find(button => button.text() === 'Retry Google setup')!.trigger('click'); await flushPromises()
  expect(mocks.load).toHaveBeenCalledTimes(2); expect(view.find('form button').attributes('disabled')).toBeUndefined()
})
it('cancels a stalled sign-in and ignores its late result after a successful retry', async () => {
  let finish!: (identity: unknown) => void
  mocks.connect.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const view = await opened(); await view.find('form').trigger('submit'); await flushPromises()
  expect(view.find('[role="status"]').text()).toContain('Waiting for Google sign-in')
  await view.findAll('button').find(button => button.text() === 'Cancel sign-in')!.trigger('click')
  expect(view.find('[role="alert"]').text()).toContain('cancelled'); expect(mocks.probe).not.toHaveBeenCalled()
  await view.find('form').trigger('submit'); await flushPromises()
  expect(view.find('[role="status"]').text()).toContain('Verified live')
  finish({ subject: 'synthetic-old-subject' }); await flushPromises()
  expect(mocks.probe).toHaveBeenCalledOnce(); expect(view.find('[role="status"]').text()).toContain('Verified live'); expect(view.find('[role="alert"]').exists()).toBe(false)
})
it('distinguishes completed sign-in from the live Drive check and reports success only after verification', async () => {
  let finish!: () => void
  mocks.probe.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve }))
  const view = await opened(); await view.find('form').trigger('submit'); await flushPromises()
  expect(view.find('[role="status"]').text()).toContain('Checking encrypted file visibility')
  expect(view.text()).not.toContain('Verified live'); expect(view.text()).not.toContain('Cancel sign-in')
  finish(); await flushPromises(); expect(view.find('[role="status"]').text()).toContain('Verified live')
})

it('offers an existing-session retry after a timeout and preserves explicit account selection on the normal path', async () => {
  mocks.connect.mockRejectedValueOnce(new Error('Google authorization timed out. Try again.'))
  const view = await opened(); await view.find('form').trigger('submit'); await flushPromises()
  expect(mocks.connect).toHaveBeenLastCalledWith(undefined); expect(mocks.probe).not.toHaveBeenCalled()
  await view.findAll('button').find(button => button.text() === 'Use existing Google sign-in')!.trigger('click'); await flushPromises()
  expect(mocks.connect).toHaveBeenLastCalledWith({ prompt: '' }); expect(mocks.probe).toHaveBeenCalledOnce(); expect(view.find('[role="status"]').text()).toContain('Verified live')
})

it('uses the desktop account as a hint only on an explicit existing-session retry', async () => {
  const view = await opened({ accountEmail: 'synthetic@example.invalid' })
  await view.find('form').trigger('submit'); await flushPromises(); expect(mocks.connect).toHaveBeenLastCalledWith(undefined)
  await view.findAll('button').find(button => button.text() === 'Use existing Google sign-in')!.trigger('click'); await flushPromises()
  expect(mocks.connect).toHaveBeenLastCalledWith({ prompt: '', loginHint: 'synthetic@example.invalid' })
})
