// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ApplicationFocus from '../../src/ApplicationFocus.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getApplication: vi.fn(), getDashboard: vi.fn(), updateApplication: vi.fn() }))
vi.mock('primevue/useconfirm', () => ({ useConfirm: () => ({ require: vi.fn() }) }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]], stubs: { ApplicationWork: true, ApplicationTimeline: true, ApplicationDocuments: true, ApplicationInterviews: true, PostingReview: true } }
const record = { id: 'app-1', revision: 1, company: 'Example', job_title: 'Engineer', date_applied: '2026-10-01', job_url: 'https://example.com/job?ref=original', email_reference: 'https://mail.google.com/mail/u/0/#all/abc\nMessage-ID: <two@example.com>', status: 'SUBMITTED', outcome: null, posting_status: 'LIVE', phone_number: null, contact_type: 'EMAIL', contact_email: 'hr@example.com', description: 'Long role description', requirements: 'Long requirements', followup_delay_days: null, max_followup_suggestions: null } as api.Application
beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.mocked(api.getApplication).mockResolvedValue({ ...record, deadline: null, deadline_kind: null })
  vi.mocked(api.getDashboard).mockResolvedValue({ upcoming: [], overdue_followups: [], due_followups: [] } as unknown as api.DashboardData)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }

it('shows a short posting link with a copy action, separate email references and closed supporting details', async () => {
  const wrapper = mount(ApplicationFocus, { props: { id: record.id }, global })
  await flushPromises()
  const overview = wrapper.get('[aria-label="Application overview"]')
  const posting = overview.get('a[target="_blank"]')
  expect(posting.text()).toBe('Job posting')
  expect(posting.attributes('href')).toBe(record.job_url)
  expect(overview.text()).not.toContain(record.job_url)
  expect(overview.findAll('.email-references a').map(link => link.text())).toEqual(['Email ref 1', 'Email ref 2'])
  expect(overview.get('details').attributes('open')).toBeUndefined()
  expect(wrapper.get('details.panel').attributes('open')).toBeUndefined()
  expect(wrapper.get('.posting-tools').attributes('open')).toBeUndefined()
  await button(wrapper, 'Copy job posting').trigger('click')
  await flushPromises()
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith(record.job_url)
  expect(wrapper.text()).toContain('Job posting link copied.')
  vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error('denied'))
  await button(wrapper, 'Copy job posting').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('Right-click Job posting')
})

it('edits and saves multiple references without submitting derived display fields', async () => {
  const wrapper = mount(ApplicationFocus, { props: { id: record.id }, global })
  await flushPromises()
  await button(wrapper, 'Edit application').trigger('click')
  const refs = wrapper.findAll('textarea').find(input => input.element.closest('label')?.textContent?.includes('Email references'))!
  await refs.setValue('First email\nSecond email')
  vi.mocked(api.updateApplication).mockResolvedValue({ ...record, email_reference: 'First email\nSecond email' })
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.updateApplication).toHaveBeenCalledWith(record.id, { email_reference: 'First email\nSecond email', expected_revision: 1 })
  expect(wrapper.findAll('.email-references a')).toHaveLength(2)
})
