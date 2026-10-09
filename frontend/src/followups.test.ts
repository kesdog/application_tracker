// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import TemplateField from './components/shared/TemplateField.vue'
import FollowUpEditor from './FollowUpEditor.vue'
import FollowUps from './FollowUps.vue'
import * as api from './api'

vi.mock('./api', async original => ({ ...await original<typeof import('./api')>(), getTemplateVariables: vi.fn(), updateFollowUp: vi.fn(), getFollowUpAIRequest: vi.fn(), getFollowUps: vi.fn(), getFollowUpNotices: vi.fn(), getWork: vi.fn(), getApplication: vi.fn(), readFollowUpNotice: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const variables = [{ key: 'company_name', label: 'Company name', group: 'Application', aliases: [] }, { key: 'position_name', label: 'Position name', group: 'Application', aliases: [] }]
const app = { id: 'job-1', company: 'Example', job_title: 'Engineer', followup_paused: false, followup_customization: {}, followup_instructions: '' } as api.Application
const item: api.FollowUp = { id: 'followup-1', application_id: app.id, sequence_number: 1, due_at: '2026-10-08T07:00:00Z', status: 'PREPARED', is_automatic: true, template_reference: null, sent_at: null, channel: 'EMAIL', subject: 'Checking in', body: 'Hello Example,\nAlex', instructions: '', template_snapshot: {}, variable_snapshot: {}, customization: {}, revision: 3, approved_revision: null, prepared_at: null, updated_at: '2026-10-01T07:00:00Z', snoozed_until: null, archived_at: null }
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(b => b.text() === text)! }
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.mocked(api.getTemplateVariables).mockResolvedValue(variables)
  vi.mocked(api.updateFollowUp).mockResolvedValue(item)
  vi.mocked(api.getFollowUps).mockResolvedValue({ items: [{ ...item, application: app }], total: 1, page: 1, page_size: 20 })
  vi.mocked(api.getFollowUpNotices).mockResolvedValue([])
  vi.mocked(api.getWork).mockResolvedValue({ followups: [item], notes: [], tasks: [], followup_delay_days: 7, max_followup_suggestions: 2 })
  vi.mocked(api.getApplication).mockResolvedValue(app)
  window.location.hash = '#/followups'
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('highlights variables while keeping pasted markup plain text', () => {
  const wrapper = mount(TemplateField, { props: { modelValue: 'Hello {company_name} <script>alert(1)</script>', label: 'Message', variables } })
  expect(wrapper.get('mark').text()).toBe('{company_name}')
  expect(wrapper.find('script').exists()).toBe(false)
  expect(wrapper.get('textarea').element.value).toContain('<script>')
})

it('searches the variable picker and replaces selected text without losing the rest', async () => {
  const wrapper = mount(TemplateField, { props: { modelValue: 'Hello NAME!', label: 'Message', variables } })
  wrapper.get('textarea').element.setSelectionRange(6, 10)
  await button(wrapper, 'Insert variable').trigger('click')
  await wrapper.get('input[type="search"]').setValue('company')
  expect(wrapper.findAll('.variable-list button')).toHaveLength(1)
  await wrapper.get('.variable-list button').trigger('click')
  expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['Hello {company_name}!'])
})

it('requires saving edits before approval and includes the loaded revision when saving', async () => {
  const wrapper = mount(FollowUpEditor, { props: { item, application: app }, global })
  await flushPromises()
  await wrapper.get('textarea[aria-label="Follow-up message"]').setValue('Updated message')
  expect(button(wrapper, 'Mark ready').attributes('disabled')).toBeDefined()
  await button(wrapper, 'Reschedule').trigger('click')
  expect(api.updateFollowUp).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('Save your message edits')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.updateFollowUp).toHaveBeenCalledWith(app.id, item.id, expect.objectContaining({ body: 'Updated message', expected_revision: 3 }))
})

it('retains edited text after a conflicting save', async () => {
  vi.mocked(api.updateFollowUp).mockRejectedValue(new Error('Changed in another session'))
  const wrapper = mount(FollowUpEditor, { props: { item, application: app }, global })
  await flushPromises()
  await wrapper.get('textarea[aria-label="Follow-up message"]').setValue('Keep this text')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect((wrapper.get('textarea[aria-label="Follow-up message"]').element as HTMLTextAreaElement).value).toBe('Keep this text')
  expect(wrapper.text()).toContain('Changed in another session')
})

it('offers selectable copy fallback without recording a send', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('Denied')) } })
  const wrapper = mount(FollowUpEditor, { props: { item, application: app }, global })
  await flushPromises()
  await button(wrapper, 'Copy message').trigger('click')
  await flushPromises()
  expect((wrapper.get('textarea[readonly]').element as HTMLTextAreaElement).value).toBe(item.body)
  expect(api.updateFollowUp).not.toHaveBeenCalled()
})

it('keeps unsaved job instructions when the saved message reloads', async () => {
  const wrapper = mount(FollowUpEditor, { props: { item, application: app }, global })
  await flushPromises()
  const reminders = wrapper.findAll('details').find(detail => detail.text().includes('Reminder controls and job instructions'))!
  await reminders.get('textarea').setValue('Mention the recruiter conversation')
  await wrapper.setProps({ item: { ...item, revision: 4, body: 'Saved message update' } })
  expect(reminders.get('textarea').element.value).toBe('Mention the recruiter conversation')
})

it('opens exact follow-up deep links and requests server filters', async () => {
  window.location.hash = `#/followups/${app.id}/${item.id}`
  const wrapper = mount(FollowUps, { global })
  await flushPromises()
  expect(wrapper.findComponent(FollowUpEditor).exists()).toBe(true)
  await wrapper.get('input[type="search"]').setValue('Example')
  await wrapper.get('form.filters').trigger('submit')
  await flushPromises()
  expect(api.getFollowUps).toHaveBeenLastCalledWith(expect.stringContaining('q=Example'))
  expect(wrapper.findAll('.queue a')[0]?.attributes('href')).toBe(`#/followups/${app.id}/${item.id}`)
})

it('groups due notices and dismisses only the notices', async () => {
  vi.mocked(api.getFollowUpNotices).mockResolvedValue([{ id: 'notice-1', followup: item, application: app }])
  vi.mocked(api.readFollowUpNotice).mockResolvedValue({ read: true })
  const wrapper = mount(FollowUps, { global })
  await flushPromises()
  expect(wrapper.text()).toContain('1 follow-up reminders need attention')
  await button(wrapper, 'Dismiss these notices').trigger('click')
  await flushPromises()
  expect(api.readFollowUpNotice).toHaveBeenCalledWith('notice-1')
  expect(api.updateFollowUp).not.toHaveBeenCalled()
})
