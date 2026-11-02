// @vitest-environment jsdom
import '../support/browser'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import FollowUpLanguages from '../../src/components/followups/FollowUpLanguages.vue'
import { setLocale } from '../../src/i18n'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getFollowUpMessageVersions: vi.fn(), switchFollowUpLanguage: vi.fn(), restoreFollowUpMessageVersion: vi.fn(), updateApplication: vi.fn() }))
enableAutoUnmount(afterEach)
const application = { id: 'job-1', revision: 3, status: 'SUBMITTED', followup_customization: { language: 'French', signature: 'Alex' } } as api.Application
const item = { id: 'message-1', revision: 5, status: 'PREPARED', channel: 'EMAIL', message_language: 'fr', template_snapshot: {}, customization: {}, content_available: true } as api.FollowUp
const versions: api.FollowUpMessageVersion[] = [
  { id: 'fr-1', language: 'fr', subject: 'Mon objet', body: 'Mon message', source_revision: 5, created_at: '2026-10-28T10:00:00Z', active: true },
  { id: 'en-1', language: 'en', subject: 'My original subject', body: 'My original message', source_revision: 2, created_at: '2026-10-28T09:00:00Z', active: false },
]
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
beforeEach(() => {
  setLocale('en'); vi.clearAllMocks()
  vi.mocked(api.getFollowUpMessageVersions).mockResolvedValue({ current_language: 'fr', versions })
  vi.mocked(api.switchFollowUpLanguage).mockResolvedValue(item)
  vi.mocked(api.restoreFollowUpMessageVersion).mockResolvedValue(item)
  vi.mocked(api.updateApplication).mockResolvedValue(application)
})
afterEach(() => setLocale('en'))

it('uses email language independently of the interface and restores a saved message with its revision', async () => {
  const wrapper = mount(FollowUpLanguages, { props: { application, item }, global })
  await flushPromises()
  expect((wrapper.findAll('select')[0]!.element as HTMLSelectElement).value).toBe('fr')
  expect(api.switchFollowUpLanguage).not.toHaveBeenCalled()
  setLocale('fr'); await flushPromises()
  expect(wrapper.text()).toContain('Versions de message enregistrées')
  expect((wrapper.findAll('select')[0]!.element as HTMLSelectElement).value).toBe('fr')
  expect(wrapper.text()).toContain('My original message')
  const restore = wrapper.findAll('button').find(button => button.text() === 'Utiliser la version enregistrée' && button.attributes('disabled') === undefined)!
  await restore.trigger('click'); await flushPromises()
  expect(api.restoreFollowUpMessageVersion).toHaveBeenCalledWith('job-1', 'message-1', 'en-1', 5)
  expect(wrapper.emitted('changed')).toHaveLength(1)
})

it('switches just this message and saves application preference separately without replacing other preferences', async () => {
  const wrapper = mount(FollowUpLanguages, { props: { application, item }, global })
  await flushPromises()
  await wrapper.findAll('select')[0]!.setValue('en')
  await wrapper.findAll('button').find(button => button.text() === 'Use this email language')!.trigger('click')
  await flushPromises()
  expect(api.switchFollowUpLanguage).toHaveBeenCalledWith('job-1', 'message-1', 'en', 5)
  expect(api.updateApplication).not.toHaveBeenCalled()
  await wrapper.findAll('select')[1]!.setValue('en')
  await wrapper.findAll('button').find(button => button.text() === 'Save application email language')!.trigger('click')
  await flushPromises()
  expect(api.updateApplication).toHaveBeenCalledWith('job-1', { expected_revision: 3, followup_customization: { language: 'English', signature: 'Alex' } })
})

it('blocks switching with unsaved edits, retains saved previews for sent mail and handles conflicts', async () => {
  const wrapper = mount(FollowUpLanguages, { props: { application, item, disabled: true }, global })
  await flushPromises()
  expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await wrapper.setProps({ disabled: false, item: { ...item, status: 'SENT' } }); await flushPromises()
  expect(wrapper.text()).toContain('My original message')
  expect(wrapper.findAll('button').find(button => button.text() === 'Use this email language')!.attributes('disabled')).toBeDefined()
  await wrapper.setProps({ item }); await flushPromises()
  vi.mocked(api.switchFollowUpLanguage).mockRejectedValue(new Error('This follow-up changed in another session. Reload before saving.'))
  await wrapper.findAll('button').find(button => button.text() === 'Use this email language')!.trigger('click')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('another session')
  expect(wrapper.emitted('changed')).toBeUndefined()
})
