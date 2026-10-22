// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import WorkspaceData from '../../src/components/settings/WorkspaceData.vue'
import * as tools from '../../src/workspaceApi'
import * as api from '../../src/api'

vi.mock('../../src/workspaceApi')
vi.mock('../../src/api', () => ({ listApplications: vi.fn() }))
beforeEach(() => vi.resetAllMocks())
const render = () => mount(WorkspaceData, { global: { plugins: [PrimeVue] } })
async function click(wrapper: ReturnType<typeof render>, text: string) {
  const button = wrapper.findAll('button').find(item => item.text().includes(text))!
  await button.trigger('click'); await flushPromises()
}
async function open(wrapper: ReturnType<typeof render>, name: string) {
  const detail = wrapper.findAll('details').find(item => item.find('summary').text() === name)!
  ;(detail.element as HTMLDetailsElement).open = true
  await detail.trigger('toggle'); await flushPromises()
}

it('requires a fresh preview after mapping edits and preserves selected rows after failure', async () => {
  vi.mocked(tools.previewImport).mockResolvedValue({ headers: ['Company'], fields: ['company', 'job_title'], mapping: { Company: 'company' }, rows: [
    { row: 2, application: { company: 'Example', job_title: 'Engineer' }, errors: [], duplicates: [] },
    { row: 3, application: {}, errors: ['Missing title'], duplicates: [] },
  ] })
  vi.mocked(tools.applyImport).mockRejectedValue(new Error('Import failed; retry safely.'))
  const wrapper = render()
  const file = wrapper.get('input[accept=".csv,.xlsx"]')
  Object.defineProperty(file.element, 'files', { value: [new File(['Company\nExample'], 'apps.csv')] })
  await file.trigger('change'); await click(wrapper, 'Preview import')
  expect(wrapper.get('input[aria-label="Import row 3"]').attributes('disabled')).toBeDefined()
  await wrapper.get('.mapping select').setValue('job_title')
  expect(wrapper.findAll('button').find(item => item.text().includes('Import 1 selected'))!.attributes('disabled')).toBeDefined()
  await click(wrapper, 'Preview import'); await click(wrapper, 'Import 1 selected')
  expect(wrapper.get('[role=alert]').text()).toContain('retry safely')
  expect((wrapper.get('input[aria-label="Import row 2"]').element as HTMLInputElement).checked).toBe(true)
  wrapper.unmount()
})

it('restores deleted work through the reviewed record revision and refreshes the list', async () => {
  const record = { id: 'record-1', revision: 7, company: 'Example', job_title: 'Engineer' } as api.Application
  let restored = false
  vi.mocked(tools.getTrash).mockImplementation(async () => restored ? { total: 0, items: [] } : { total: 1, items: [record] })
  vi.mocked(tools.restoreApplication).mockImplementation(async () => { restored = true; return {} })
  const wrapper = render(); await open(wrapper, 'Deleted applications'); await click(wrapper, 'Restore')
  expect(tools.restoreApplication).toHaveBeenCalledWith(record)
  expect(wrapper.text()).toContain('restored with reminders paused')
  expect(wrapper.text()).toContain('No deleted applications')
  wrapper.unmount()
})

it('offers full backup download without attempting to replace the active workspace', async () => {
  vi.mocked(tools.downloadBackup).mockResolvedValue(undefined)
  const wrapper = render(); await click(wrapper, 'Download full backup')
  expect(tools.downloadBackup).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('Keep an off-device copy')
  expect(wrapper.text()).toContain('open workspace is never overwritten')
  wrapper.unmount()
})
