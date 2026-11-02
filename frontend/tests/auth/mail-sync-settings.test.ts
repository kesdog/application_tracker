// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import MailSyncSettings from '../../src/components/settings/MailSyncSettings.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getGeneralSettings: vi.fn(), saveGeneralSettings: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const defaults: api.GeneralSettings = { subject_template:'Subject',body_template:'Body',signature:'Alex',language:'English',tone:'Friendly',instructions:'Keep me',followup_delay_days:7,max_followup_suggestions:2,unsuccessful_review_after:3,recipient_page_limit:6,mail_sync_max_messages:100,timezone:'Europe/Paris',reminder_time:'09:00',notifications_enabled:true,quiet_start:'20:00',quiet_end:'08:00',daily_digest:true,revision:1 }
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.getGeneralSettings).mockResolvedValue({ ...defaults }) })

it('loads the saved limit and preserves current unrelated settings when saving', async () => {
 const wrapper=mount(MailSyncSettings,{global});await flushPromises()
 const input=wrapper.get('input[role=spinbutton]')
 expect(wrapper.find(`label[for="${input.element.id}"]`).exists()).toBe(true)
 expect(input.attributes('aria-describedby')).toBe(wrapper.get('p[id]').attributes('id'))
 expect((input.element as HTMLInputElement).value).toBe('100')
 await input.setValue('25');await input.trigger('blur')
 vi.mocked(api.getGeneralSettings).mockResolvedValue({...defaults,signature:'Updated elsewhere',revision:2})
 vi.mocked(api.saveGeneralSettings).mockResolvedValue({...defaults,signature:'Updated elsewhere',mail_sync_max_messages:25,revision:3})
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(api.saveGeneralSettings).toHaveBeenCalledWith(expect.objectContaining({mail_sync_max_messages:25,signature:'Updated elsewhere',instructions:'Keep me',revision:2}))
 expect(wrapper.text()).toContain('applies to the next sync')
})

it('rejects an empty allowance without submitting preferences', async () => {
 const wrapper=mount(MailSyncSettings,{global});await flushPromises()
 const input=wrapper.get('input[role=spinbutton]')
 await input.setValue('');await input.trigger('blur')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(api.saveGeneralSettings).not.toHaveBeenCalled()
 expect(wrapper.get('[role=alert]').text()).toContain('whole number')
})

it('saves the absolute application date boundary with the existing allowance', async () => {
 const wrapper=mount(MailSyncSettings,{global});await flushPromises()
 expect((wrapper.get('input[type=date]').element as HTMLInputElement).value).toBe('2026-01-01')
 await wrapper.get('input[type=date]').setValue('2026-06-01')
 vi.mocked(api.saveGeneralSettings).mockResolvedValue({...defaults,mail_sync_not_before:'2026-06-01'})
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(api.saveGeneralSettings).toHaveBeenCalledWith(expect.objectContaining({mail_sync_not_before:'2026-06-01',mail_sync_max_messages:100}))
})

it('keeps the chosen limit on a revision conflict and reports a failed initial load', async () => {
 vi.mocked(api.getGeneralSettings).mockRejectedValueOnce(new Error('Offline'))
 const wrapper=mount(MailSyncSettings,{global});await flushPromises()
 expect(wrapper.get('[role=alert]').text()).toContain('Could not load')
 await wrapper.findAll('button').find(b=>b.text()==='Reload mail scan limit')!.trigger('click');await flushPromises()
 const input=wrapper.get('input[role=spinbutton]')
 await input.setValue('50');await input.trigger('blur')
 vi.mocked(api.saveGeneralSettings).mockRejectedValue(new Error('Settings changed in another session. Reload before saving.'))
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(wrapper.get('[role=alert]').text()).toContain('Settings changed')
 expect((input.element as HTMLInputElement).value).toBe('50')
})
