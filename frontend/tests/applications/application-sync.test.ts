// @vitest-environment jsdom
import '../support/browser'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ApplicationSyncControl from '../../src/components/applications/ApplicationSyncControl.vue'
import { getApplicationSync, startApplicationSync, type ApplicationSyncStatus } from '../../src/api'
vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getApplicationSync:vi.fn(), startApplicationSync:vi.fn() }))
enableAutoUnmount(afterEach)
const global={plugins:[[PrimeVue,{unstyled:true}] as [typeof PrimeVue,{unstyled:boolean}]],stubs:{teleport:true}}
const idle:ApplicationSyncStatus={id:null,state:'IDLE',phase:null,created:0,updated:0,checked:0,review_count:0,gmail:'NOT_RUN',drive:'NOT_RUN',warnings:[],finished_at:null}
beforeEach(()=>{vi.useFakeTimers();vi.clearAllMocks();vi.mocked(getApplicationSync).mockResolvedValue(idle)})
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()})

it('runs both phases, blocks duplicate presses, and refreshes the list only after completion',async()=>{
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 const running={...idle,id:'job',state:'RUNNING' as const,phase:'GMAIL' as const}
 vi.mocked(startApplicationSync).mockResolvedValue(running)
 await wrapper.get('button').trigger('click');await flushPromises()
 expect(startApplicationSync).toHaveBeenCalledTimes(1)
 expect(wrapper.get('button').attributes('disabled')).toBeDefined()
 expect(wrapper.text()).toContain('Checking Gmail')
 vi.mocked(getApplicationSync).mockResolvedValue({...running,phase:'DRIVE',created:2,updated:3,checked:7})
 await vi.advanceTimersByTimeAsync(1000);await flushPromises()
 expect(wrapper.text()).toContain('Synchronizing tracker records')
 expect(wrapper.emitted('changed')).toBeUndefined()
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,id:'job',state:'COMPLETED',created:2,updated:3,checked:7,gmail:'COMPLETED',drive:'COMPLETED'})
 await vi.advanceTimersByTimeAsync(1000);await flushPromises()
 expect(wrapper.text()).toContain('2 new · 3 updated applications')
 expect(wrapper.text()).toContain('Drive synchronized')
 expect(wrapper.emitted('changed')).toHaveLength(1)
 expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
})

it('shows partial completion and review links without claiming both sources synchronized',async()=>{
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 vi.mocked(startApplicationSync).mockResolvedValue({...idle,id:'partial',state:'PARTIAL',gmail:'COMPLETED',drive:'SETUP_REQUIRED',created:1,review_count:1,warnings:['Set up Drive sync.'],reviews:[{message_id:'abc',subject:'Unclear application',reason:'Several applications match.',url:'https://mail.google.com/mail/u/0/#all/abc'}]})
 await wrapper.get('button').trigger('click');await flushPromises()
 expect(wrapper.text()).toContain('1 new')
 expect(wrapper.text()).toContain('Drive sync needs attention')
 expect(wrapper.find('a[href="#/settings?tab=connections"]').exists()).toBe(true)
 expect(wrapper.find('a[href="#/settings?tab=data"]').exists()).toBe(true)
 expect(wrapper.get('details summary').text()).toContain('1 email needs review')
 expect(wrapper.get('a[target="_blank"]').attributes('href')).toContain('#all/abc')
 expect(wrapper.emitted('changed')).toHaveLength(1)
})

it('resumes polling an existing run and does not update an unmounted page',async()=>{
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,state:'RUNNING',phase:'GMAIL'})
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 expect(wrapper.get('button').attributes('disabled')).toBeDefined()
 wrapper.unmount()
 await vi.advanceTimersByTimeAsync(5000)
 expect(getApplicationSync).toHaveBeenCalledTimes(1)
 expect(startApplicationSync).not.toHaveBeenCalled()
})

it('shows the saved mail boundary after reopening the page',async()=>{
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,gmail_checked_through:'2026-10-27T18:00:00Z'})
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 expect(wrapper.text()).toContain('Gmail checked through')
 expect(wrapper.text()).toContain('Future syncs check newer mail.')
 expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
})

it('offers continuation for capped runs and does not claim remaining mail was checked',async()=>{
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,id:'capped',state:'PARTIAL',gmail:'LIMIT_REACHED',drive:'COMPLETED',checked:25,mail_limit:25,limit_reached:true,gmail_checked_through:'2026-10-27T18:00:00Z'})
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 expect(wrapper.get('button').text()).toContain('Continue sync')
 expect(wrapper.text()).toContain('Reached the 25-email limit')
 expect(wrapper.text()).toContain('Remaining mail has not been marked as checked')
 expect(wrapper.text()).not.toContain('Future syncs check newer mail')
 expect(wrapper.get('a[href="#/settings?tab=connections"]').text()).toContain('Mail scan limit')
 vi.mocked(startApplicationSync).mockResolvedValue({...idle,id:'next',state:'RUNNING',phase:'GMAIL',mail_limit:25})
 await wrapper.get('button').trigger('click');await flushPromises()
 expect(startApplicationSync).toHaveBeenCalledOnce()
 expect(wrapper.get('button').attributes('disabled')).toBeDefined()
})

it('prompts before the first Gmail scan with a three-month default and supports cancel',async()=>{
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,initial_scan_required:true,gmail_account:'person@example.com'})
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 await wrapper.get('button').trigger('click');await flushPromises()
 const dialog=wrapper.get('[role=dialog]')
 expect(dialog.text()).toContain('person@example.com')
 expect((dialog.get('input[role=spinbutton]').element as HTMLInputElement).value).toBe('3')
 expect(startApplicationSync).not.toHaveBeenCalled()
 await dialog.findAll('button').find(b=>b.text()==='Cancel')!.trigger('click');await flushPromises()
 expect(wrapper.find('[role=dialog]').exists()).toBe(false)
 expect(startApplicationSync).not.toHaveBeenCalled()
})

it('submits the chosen first-run months and continues capped jobs without asking again',async()=>{
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,initial_scan_required:true,gmail_account:'person@example.com'})
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 await wrapper.get('button').trigger('click');await flushPromises()
 const dialog=wrapper.get('[role=dialog]')
 const input=dialog.get('input[role=spinbutton]')
 expect(input.element.id).toBe(dialog.get('label').attributes('for'))
 await input.setValue('6');await input.trigger('blur')
 const capped={...idle,state:'PARTIAL' as const,gmail:'LIMIT_REACHED',limit_reached:true,mail_limit:100,initial_scan_required:false,gmail_scan_from:'2026-04-28T12:00:00Z',lookback_months:6}
 vi.mocked(startApplicationSync).mockResolvedValue(capped)
 await dialog.get('form').trigger('submit');await flushPromises()
 expect(startApplicationSync).toHaveBeenCalledWith({lookback_months:6})
 expect(wrapper.find('[role=dialog]').exists()).toBe(false)
 expect(wrapper.text()).toContain('Initial mail scan starts from')
 vi.mocked(getApplicationSync).mockResolvedValue(capped)
 await wrapper.get('button').trigger('click');await flushPromises()
 expect(startApplicationSync).toHaveBeenLastCalledWith(undefined)
 expect(wrapper.find('[role=dialog]').exists()).toBe(false)
})

it('requires a fresh first-run choice when the connected account changes while the dialog is open',async()=>{
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,initial_scan_required:true,gmail_account:'first@example.com'})
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 await wrapper.get('button').trigger('click');await flushPromises()
 const input=wrapper.get('input[role=spinbutton]')
 await input.setValue('9');await input.trigger('blur')
 vi.mocked(getApplicationSync).mockResolvedValue({...idle,initial_scan_required:true,gmail_account:'second@example.com'})
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(startApplicationSync).not.toHaveBeenCalled()
 expect(wrapper.get('[role=dialog]').text()).toContain('second@example.com')
 expect((wrapper.get('input[role=spinbutton]').element as HTMLInputElement).value).toBe('3')
})

it('does not start when the first-run status cannot be refreshed',async()=>{
 const wrapper=mount(ApplicationSyncControl,{global});await flushPromises()
 vi.mocked(getApplicationSync).mockRejectedValue(new Error('Unavailable'))
 await wrapper.get('button').trigger('click');await flushPromises()
 expect(startApplicationSync).not.toHaveBeenCalled()
 expect(wrapper.get('[role=alert]').text()).toContain('Unavailable')
})
