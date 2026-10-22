// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ApplicationSyncControl from '../../src/components/applications/ApplicationSyncControl.vue'
import { getApplicationSync, startApplicationSync, type ApplicationSyncStatus } from '../../src/api'
vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getApplicationSync:vi.fn(), startApplicationSync:vi.fn() }))
enableAutoUnmount(afterEach)
const global={plugins:[[PrimeVue,{unstyled:true}] as [typeof PrimeVue,{unstyled:boolean}]]}
const idle:ApplicationSyncStatus={id:null,state:'IDLE',phase:null,created:0,updated:0,checked:0,review_count:0,gmail:'NOT_RUN',drive:'NOT_RUN',warnings:[],finished_at:null}
beforeEach(()=>{vi.useFakeTimers();vi.clearAllMocks();vi.mocked(getApplicationSync).mockResolvedValue(idle)})
afterEach(()=>vi.useRealTimers())

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
 expect(wrapper.find('a[href="#/settings"]').exists()).toBe(true)
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
