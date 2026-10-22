// @vitest-environment jsdom
import { enableAutoUnmount, mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import SyncSettings from '../../src/components/sync/SyncSettings.vue'
import { syncClient } from '../../src/syncClient'

vi.mock('../../src/syncClient', () => ({ syncClient: {
  status: vi.fn(), conflicts: vi.fn(), initialize: vi.fn(), run: vi.fn(), resolve: vi.fn(),
} }))
const status = { initialized: false, pending_uploads: 0, pending_downloads: 0, conflicts: 0 }
enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(syncClient.status).mockResolvedValue({ ...status })
  vi.mocked(syncClient.conflicts).mockResolvedValue([])
})
function button(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find(item => item.text().includes(text))!
}

it('requires Drive and explicit storage consent before generating the recovery export', async () => {
  const wrapper = mount(SyncSettings, { props: { driveReady: false } })
  await flushPromises()
  expect(button(wrapper, 'Initialize sync').attributes('disabled')).toBeDefined()
  await wrapper.setProps({ driveReady: true })
  expect(button(wrapper, 'Initialize sync').attributes('disabled')).toBeDefined()
  await wrapper.get('input[type=checkbox]').setValue(true)
  vi.mocked(syncClient.initialize).mockResolvedValue({ workspace_id: 'workspace', recovery_export: 'ats1.test.recovery' })
  vi.mocked(syncClient.status).mockResolvedValue({ ...status, initialized: true })
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(syncClient.initialize).toHaveBeenCalledWith('Desktop', null)
  expect(wrapper.get('textarea').element.value).toBe('ats1.test.recovery')
  await button(wrapper, 'I saved it').trigger('click')
  expect(wrapper.find('textarea').exists()).toBe(false)
})

it('preserves conflict review after a stale resolution response', async () => {
  const conflict = { id: 'conflict', record_key: 'application:record', heads: ['left', 'right'], reason: 'competing_values',
    base: { company: 'Original' }, variants: [
      { head: 'left', device_id: 'device-left', actor: 'HUMAN', state: { company: 'Left' } },
      { head: 'right', device_id: 'device-right', actor: 'HUMAN', state: { company: 'Right' } },
    ] }
  vi.mocked(syncClient.status).mockResolvedValue({ ...status, initialized: true, conflicts: 1 })
  vi.mocked(syncClient.conflicts).mockResolvedValue([conflict])
  vi.mocked(syncClient.resolve).mockRejectedValue(new Error('Conflict changed. Refresh.'))
  const wrapper = mount(SyncSettings, { props: { driveReady: true } })
  await flushPromises()
  expect(wrapper.get('select').text()).toContain('common ancestor')
  await wrapper.get('select').setValue(JSON.stringify('Right'))
  expect(button(wrapper, 'Save reviewed resolution').attributes('disabled')).toBeDefined()
  await wrapper.get('.conflict input[type=checkbox]').setValue(true)
  await button(wrapper, 'Refresh sync status').trigger('click')
  await flushPromises()
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(JSON.stringify('Right'))
  expect((wrapper.get('.conflict input[type=checkbox]').element as HTMLInputElement).checked).toBe(true)
  // Reviewing one value must not authorize a subsequently changed value.
  await wrapper.get('select').setValue(JSON.stringify('Left'))
  expect(button(wrapper, 'Save reviewed resolution').attributes('disabled')).toBeDefined()
  await wrapper.get('select').setValue(JSON.stringify('Right'))
  await wrapper.get('.conflict input[type=checkbox]').setValue(true)
  await button(wrapper, 'Save reviewed resolution').trigger('click')
  await flushPromises()
  expect(syncClient.resolve).toHaveBeenCalledWith(conflict, { company: 'Right' })
  expect(wrapper.text()).toContain('Conflict changed')
  expect(wrapper.find('.conflict').exists()).toBe(true)
})
