// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import AIResults from '../../src/components/followups/AIResults.vue'
import FollowUps from '../../src/FollowUps.vue'
import FollowUpSettings from '../../src/components/settings/FollowUpSettings.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(),
  getFollowUpAIResults: vi.fn(), importFollowUpAIResult: vi.fn(), getOutcomeReviews: vi.fn(), getFollowUps: vi.fn(), getFollowUpNotices: vi.fn(),
  getRecipientQueue: vi.fn(),
  getGeneralSettings: vi.fn(), getTemplateVariables: vi.fn(), listApplications: vi.fn(), previewTemplate: vi.fn(), saveGeneralSettings: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const props = { applicationId: 'app-1', followupId: 'followup-1', revision: 2 }
const result: api.FollowUpAIResult = { operation_id: 'op-1', expected_revision: 2, status: 'mailbox_draft_created', agent_name: 'Claude', details: 'Saved, not sent', draft_reference: 'gmail:draft-123', accepted_revision: 2, recorded_at: '2026-10-09T10:00:00Z', reported_by: 'AGENT' }
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getFollowUpAIResults).mockResolvedValue([result])
  vi.mocked(api.getFollowUps).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  vi.mocked(api.getFollowUpNotices).mockResolvedValue([])
  vi.mocked(api.getRecipientQueue).mockResolvedValue({ queued: 0, running: 0, failed: 0, missing_followups: 0, concurrency_limit: 5, available: true })
  vi.mocked(api.getOutcomeReviews).mockResolvedValue({ items: [{ application: { id: 'app-1', company: 'Example', job_title: 'Engineer' }, threshold: 3, unanswered_sent_count: 3, needs_review: true, last_reply_at: null }], total: 1, page: 1, page_size: 20 })
  window.location.hash = '#/followups'
})

it('shows draft references as text and retains a stale result for reconciliation', async () => {
  vi.mocked(api.importFollowUpAIResult).mockRejectedValue(new Error('The message or job context changed'))
  const wrapper = mount(AIResults, { props, global })
  await flushPromises()
  expect(wrapper.text()).toContain('gmail:draft-123')
  expect(wrapper.text()).toContain('mailbox draft created')
  expect(wrapper.text()).toContain('manual sending')
  const input = JSON.stringify({ operation_id: 'op-1', expected_revision: 2, status: 'revised_message', body: 'Agent text' })
  await wrapper.get('textarea').setValue(input)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('textarea').element.value).toBe(input)
  expect(wrapper.text()).toContain('context changed')
  expect(wrapper.emitted('changed')).toBeUndefined()
})

it('imports a result without recording ready or sent and rejects invalid JSON locally', async () => {
  vi.mocked(api.importFollowUpAIResult).mockResolvedValue(result)
  const wrapper = mount(AIResults, { props, global })
  await flushPromises()
  await wrapper.get('textarea').setValue('[]')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.importFollowUpAIResult).not.toHaveBeenCalled()
  await wrapper.get('textarea').setValue(JSON.stringify({ operation_id: 'op-1', expected_revision: 2, status: 'skipped', details: 'Need mailbox tools' }))
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.importFollowUpAIResult).toHaveBeenCalledWith('app-1', 'followup-1', expect.objectContaining({ status: 'skipped' }))
  expect(wrapper.get('textarea').element.value).toBe('')
  expect(wrapper.emitted('changed')).toHaveLength(1)
})

it('shows outcome review even when there are no unsent follow-ups', async () => {
  const wrapper = mount(FollowUps, { global })
  await flushPromises()
  expect(wrapper.text()).toContain('application may be unsuccessful')
  expect(wrapper.text()).toContain('These applications stay open')
  expect(wrapper.get('a[href="#/applications/app-1"]').text()).toContain('Example')
  expect(wrapper.text()).toContain('3 unanswered follow-ups')
})

it('saves the adjustable review threshold in general settings', async () => {
  const settings: api.GeneralSettings = { subject_template: 'Hello', body_template: 'Message', signature: 'Alex', language: 'English', tone: 'Friendly', instructions: '', followup_delay_days: 7, max_followup_suggestions: 2, unsuccessful_review_after: 3, timezone: 'Europe/Paris', reminder_time: '09:00', notifications_enabled: true, quiet_start: '20:00', quiet_end: '08:00', daily_digest: true, revision: 1 }
  vi.mocked(api.getGeneralSettings).mockResolvedValue(settings)
  vi.mocked(api.getTemplateVariables).mockResolvedValue([])
  vi.mocked(api.listApplications).mockResolvedValue([])
  vi.mocked(api.previewTemplate).mockResolvedValue({ subject: { text: 'Hello', missing: [], unknown: [] }, body: { text: 'Message', missing: [], unknown: [] }, variables: {} })
  vi.mocked(api.saveGeneralSettings).mockResolvedValue({ ...settings, unsuccessful_review_after: 5, revision: 2 })
  const wrapper = mount(FollowUpSettings, { global })
  await flushPromises()
  const label = wrapper.findAll('label').find(l => l.text().includes('Review as possibly unsuccessful'))!
  expect(label.get('input').element.value).toBe('3')
  await label.get('input').setValue('5')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.saveGeneralSettings).toHaveBeenCalledWith(expect.objectContaining({ unsuccessful_review_after: 5 }))
  expect(wrapper.text()).toContain('application stays open')
})
