// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import Select from 'primevue/select'
import AddApplication from './AddApplication.vue'
import { createApplication, listApplications, validateContact, type Application } from './api'
import { applicationPayload, blankApplicationDraft, blankWizardOptions, wizardErrors } from './applicationWizard'
import { historyValues } from './settings/applicationAddressBook'

vi.mock('./api', async importOriginal => ({ ...await importOriginal<typeof import('./api')>(), createApplication: vi.fn(), listApplications: vi.fn(), validateContact: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.mocked(listApplications).mockReset().mockResolvedValue([])
  vi.mocked(createApplication).mockReset().mockImplementation(async payload => ({ ...payload, id: 'saved', duplicate_warnings: [] }) as unknown as Application)
  vi.mocked(validateContact).mockReset().mockImplementation(async data => data)
})
afterEach(() => vi.unstubAllGlobals())

it('validates essential step fields and drops unchecked optional sections without erasing their drafts', () => {
  const draft = blankApplicationDraft()
  const options = blankWizardOptions()
  expect(wizardErrors(1, draft, options)).toHaveProperty('job_title')
  draft.job_title = 'Engineer'; draft.company = 'Example'; draft.email_reference = 'Message 123'
  draft.description = 'Hidden note'; draft.phone_number = 'bad'; draft.contact_email = 'bad'; draft.deadline = '2026-10-20'
  expect(applicationPayload(draft, options)).toMatchObject({ contact_type: 'EMAIL', phone_number: null, contact_email: null, description: null, deadline: null, deadline_kind: null })
  options.deadline = true; draft.deadline = '2026-02-30'
  expect(wizardErrors(2, draft, options).deadline).toContain('valid deadline')
  draft.deadline = '2026-10-20'
  expect(applicationPayload(draft, options).deadline).toBe('2026-10-20')
})

it('deduplicates suggestions, keeps free entry and includes numeric zero from existing records', () => {
  const records = [{ company: ' Example ', location: 'Paris', followup_delay_days: 0 }, { company: 'example', location: 'Lyon', followup_delay_days: 7 }] as Application[]
  expect(historyValues(records, 'company')).toEqual(['Example'])
  expect(historyValues(records, 'location')).toEqual(['Paris', 'Lyon'])
  expect(historyValues(records, 'followup_delay_days')).toEqual(['0', '7'])
})

async function advance(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}
async function fillRole(wrapper: ReturnType<typeof mount>) {
  const inputs = wrapper.findAll('input').filter(input => input.attributes('role') === 'combobox')
  await inputs[0]!.setValue('Engineer')
  await inputs[1]!.setValue('Example')
  await advance(wrapper)
}
async function fillPosting(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('input[type="url"]').setValue('https://example.com/jobs/1')
  await advance(wrapper)
}

it('keeps drafts across Back, reaches Review without saving, and saves only after confirmation', async () => {
  const wrapper = mount(AddApplication, { global })
  await flushPromises()
  await advance(wrapper)
  expect(wrapper.text()).toContain('Enter the job title')
  await fillRole(wrapper)
  expect(wrapper.text()).toContain('Keep the posting and its evidence')
  await fillPosting(wrapper)
  expect(wrapper.text()).toContain('Add only the details you need')
  await wrapper.findAll('button').find(button => button.text() === 'Back')!.trigger('click')
  await flushPromises()
  expect((wrapper.get('input[type="url"]').element as HTMLInputElement).value).toBe('https://example.com/jobs/1')
  await advance(wrapper)
  await advance(wrapper)
  expect(wrapper.text()).toContain('Ready to add this opportunity')
  expect(createApplication).not.toHaveBeenCalled()
  await advance(wrapper)
  expect(createApplication).toHaveBeenCalledTimes(1)
  expect(wrapper.text()).toContain('Application saved')
})

it('validates contact email through the server and prevents invalid contact from reaching Review', async () => {
  const wrapper = mount(AddApplication, { global })
  await fillRole(wrapper); await fillPosting(wrapper)
  await wrapper.get('input#has-contact').setValue(true)
  await wrapper.get('input[type="email"]').setValue('invalid-email')
  vi.mocked(validateContact).mockRejectedValue(new Error('Enter a valid email address'))
  await advance(wrapper)
  expect(wrapper.text()).toContain('Enter a valid email address')
  expect(wrapper.get('.step-count').text()).toBe('Step 3 of 4')
  expect(createApplication).not.toHaveBeenCalled()
  await wrapper.get('input#has-contact').setValue(false)
  await advance(wrapper)
  await advance(wrapper)
  expect(createApplication).toHaveBeenCalledWith(expect.objectContaining({ contact_email: null, phone_number: null }))
})

it('reuses legacy phone-only contacts without changing the employer or requiring an unknown email', async () => {
  vi.mocked(listApplications).mockResolvedValue([{ id: 'previous', company: 'Previous employer', contact_type: 'EMAIL', contact_name: 'Recruiter', phone_number: '+33612345678', contact_email: null }] as Application[])
  const wrapper = mount(AddApplication, { global })
  await flushPromises()
  await fillRole(wrapper); await fillPosting(wrapper)
  await wrapper.get('input#has-contact').setValue(true)
  wrapper.findAllComponents(Select).find(select => select.props('inputId') === 'saved-contact')!.vm.$emit('update:modelValue', 'previous')
  await flushPromises()
  expect(wrapper.find('input[type="email"]').exists()).toBe(false)
  expect((wrapper.get('input[type="tel"]').element as HTMLInputElement).value).toBe('+33612345678')
  await advance(wrapper); await advance(wrapper)
  expect(createApplication).toHaveBeenCalledWith(expect.objectContaining({ company: 'Example', contact_name: 'Recruiter', contact_type: 'PHONE', phone_number: '+33612345678' }))
})
