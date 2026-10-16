// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import RecipientPicker from '../../src/components/followups/RecipientPicker.vue'
import FollowUps from '../../src/FollowUps.vue'
import * as api from '../../src/api'
vi.mock('../../src/api',async original => ({...await original<typeof import('../../src/api')>(),getRecipientState:vi.fn(),fetchRecipients:vi.fn(),chooseRecipient:vi.fn(),updateFollowUp:vi.fn(),getRecipientQueue:vi.fn(),fetchMissingRecipients:vi.fn(),getFollowUps:vi.fn(),getFollowUpNotices:vi.fn(),getOutcomeReviews:vi.fn()}))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const followup:api.RecipientFollowUp={id:'followup-1',sequence_number:1,revision:2,recipient_email:null,recipient_name:null}
const candidate:api.RecipientCandidate={id:'candidate-1',name:null,email:'jobs@example.com',kind:'recruiter_hr',role:null,source_url:'https://example.com/careers',evidence:'Public recruitment contact',company_match:'domain_name',vacancy_match:'unconfirmed',email_status:'published',stale:false,context_current:true}
const state:api.RecipientState={job:null,candidates:[candidate],missing_followups:1,followups:[followup]}
function button(w:ReturnType<typeof mount>,label:string){return w.findAll('button').find(b=>b.text()===label)!}
beforeEach(()=>{
 vi.clearAllMocks()
 vi.mocked(api.getRecipientState).mockResolvedValue(state)
 vi.mocked(api.fetchRecipients).mockResolvedValue({id:'job-1',state:'QUEUED',attempts:0,error:null,warnings:[]})
 vi.mocked(api.getRecipientQueue).mockResolvedValue({queued:0,running:0,failed:0,missing_followups:8,concurrency_limit:5,available:true})
 vi.mocked(api.getFollowUps).mockResolvedValue({items:[],total:0,page:1,page_size:20})
 vi.mocked(api.getFollowUpNotices).mockResolvedValue([])
 vi.mocked(api.getOutcomeReviews).mockResolvedValue({items:[],total:0,page:1,page_size:20})
 window.location.hash='#/followups'
})
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()})

it('shows missing-recipient state, sources and a queued spinner without selecting automatically',async()=>{
 const wrapper=mount(RecipientPicker,{props:{applicationId:'app-1'},global})
 await flushPromises()
 expect(wrapper.text()).toContain('still need a recipient')
 expect(wrapper.get('a').attributes('href')).toBe(candidate.source_url)
 expect(api.chooseRecipient).not.toHaveBeenCalled()
 vi.mocked(api.getRecipientState).mockResolvedValue({...state,job:{id:'job-1',state:'QUEUED',attempts:0,error:null,warnings:[]}})
 await button(wrapper,'Fetch recipients').trigger('click')
 await flushPromises()
 expect(api.fetchRecipients).toHaveBeenCalledWith('app-1')
 expect(wrapper.get('[role="status"]').text()).toContain('queued')
 expect(button(wrapper,'Fetch recipients again').attributes('disabled')).toBeDefined()
})

it('chooses a published candidate with the loaded revision and rejects unavailable email choices',async()=>{
 const person={...candidate,id:'person',name:'Damien Mat',email:null,kind:'technical_lead' as const}
 vi.mocked(api.getRecipientState).mockResolvedValue({...state,candidates:[candidate,person]})
 const wrapper=mount(RecipientPicker,{props:{applicationId:'app-1'},global})
 await flushPromises()
 const actions=wrapper.findAll('button').filter(b=>b.text()==='Use this recipient')
 expect(actions[1]!.attributes('disabled')).toBeDefined()
 await actions[0]!.trigger('click')
 await flushPromises()
 expect(api.chooseRecipient).toHaveBeenCalledWith('app-1','followup-1','candidate-1',2)
 expect(wrapper.emitted('changed')).toHaveLength(1)
})

it('preserves manual entries when a search finishes and when a conflicting save fails',async()=>{
 vi.useFakeTimers()
 vi.mocked(api.getRecipientState).mockResolvedValue({...state,job:{id:'job-1',state:'RUNNING',attempts:1,error:null,warnings:[]}})
 const wrapper=mount(RecipientPicker,{props:{applicationId:'app-1'},global})
 await flushPromises()
 await wrapper.get('input[type="email"]').setValue('mine@example.com')
 vi.mocked(api.getRecipientState).mockResolvedValue({...state,job:{id:'job-1',state:'COMPLETED',attempts:1,error:null,warnings:[]}})
 await vi.advanceTimersByTimeAsync(2000)
 await flushPromises()
 expect((wrapper.get('input[type="email"]').element as HTMLInputElement).value).toBe('mine@example.com')
 vi.mocked(api.updateFollowUp).mockRejectedValue(new Error('Message changed. Reload.'))
 await wrapper.get('form').trigger('submit')
 await flushPromises()
 expect((wrapper.get('input[type="email"]').element as HTMLInputElement).value).toBe('mine@example.com')
 expect(wrapper.text()).toContain('Message changed')
})

it('queues all missing jobs once and displays the five-at-a-time progress',async()=>{
 vi.mocked(api.fetchMissingRecipients).mockResolvedValue({queued:8,applications:8,concurrency_limit:5})
 const wrapper=mount(FollowUps,{global})
 await flushPromises()
 vi.mocked(api.getRecipientQueue).mockResolvedValue({queued:3,running:5,failed:0,missing_followups:8,concurrency_limit:5,available:true})
 await button(wrapper,'Fetch missing recipients').trigger('click')
 await flushPromises()
 expect(api.fetchMissingRecipients).toHaveBeenCalledTimes(1)
 expect(wrapper.text()).toContain('5 finding recipients · 3 queued · maximum 5 running')
 expect(wrapper.text()).toContain('8 recipient searches queued')
 await wrapper.get('.recipient-status select').setValue('missing')
 await flushPromises()
 expect(api.getFollowUps).toHaveBeenLastCalledWith(expect.stringContaining('recipient=missing'))
})

it('shows ranked categories, vacancy evidence and profile leads without implying verified delivery',async()=>{
 vi.mocked(api.getRecipientState).mockResolvedValue({...state,candidates:[
  {...candidate,kind:'general_contact',contact_priority:{category:'general_company_mailbox',score:120,recommended_action:'verify_recruitment_purpose',outreach_eligible:false}},
  {...candidate,id:'named',name:'Jane Recruiter',email:null,vacancy_match:'published_for_vacancy',profile_urls:[{url:'https://example.com/profile/jane',label:'Jane profile'}],contact_priority:{category:'named_recruiter',score:400,recommended_action:'find_contact_method',outreach_eligible:false}},
 ]})
 const wrapper=mount(RecipientPicker,{props:{applicationId:'app-1'},global})
 await flushPromises()
 expect(wrapper.text()).toContain('General mailbox · verify recruitment purpose')
 expect(wrapper.text()).toContain('Named recruiter')
 expect(wrapper.text()).toContain('Source names this contact for the vacancy')
 expect(wrapper.text()).toContain('Employer identity needs verification')
 expect(wrapper.text()).toContain('deliverability has not been checked')
 expect(wrapper.findAll('a').some(a=>a.attributes('href')==='https://example.com/profile/jane')).toBe(true)
 expect(api.chooseRecipient).not.toHaveBeenCalled()
})
