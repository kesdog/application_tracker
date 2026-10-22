// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ApplicationTimeline from '../../src/ApplicationTimeline.vue'
import { getTimeline, type Timeline, type TimelineEvent } from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getTimeline: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]], stubs: { DateTimeField: true } }
const event = { id:'event-1', application_id:'app-1', event_type:'MANUAL', summary:'[Gmail:abc123] Confirmation https://mail.google.com/mail/u/0/#all/abc123 https://mail.google.com/mail/u/0/#all/def456', created_at:'2026-10-18T09:00:00Z', actor_type:'AGENT', actor_reference:'agent-token', metadata:{} } as TimelineEvent

it('deduplicates equivalent email references and dates while preserving original editable event text', async () => {
  const submitted = { ...event, id:'event-2', event_type:'APPLICATION_SUBMITTED', summary:'Application submitted on 2026-10-01', metadata:{ date_only:true, date_applied:'2026-10-01' } }
  const customActor = { ...event, id:'event-3', event_type:'APPLICATION_UPDATED', summary:'Application details updated', actor_reference:'Research assistant' }
  vi.mocked(getTimeline).mockResolvedValue({ events:[event, submitted, customActor], undo_available:false } as Timeline)
  const wrapper = mount(ApplicationTimeline, { props:{ applicationId:'app-1', embedded:true }, global })
  await flushPromises()
  expect(wrapper.find('h3').exists()).toBe(false)
  expect(wrapper.text()).toContain('3 events')
  expect(wrapper.get('.event-heading strong').text()).toContain('Confirmation')
  expect(wrapper.get('.event-heading strong').text()).not.toContain('[Gmail:')
  expect(wrapper.findAll('.email-references a').map(link => link.attributes('href'))).toEqual(['https://mail.google.com/mail/u/0/#all/abc123', 'https://mail.google.com/mail/u/0/#all/def456'])
  expect(wrapper.text().split('2026-10-01')).toHaveLength(2)
  expect(wrapper.text()).not.toContain('agent-token')
  expect(wrapper.text()).toContain('Research assistant')
  expect(wrapper.findAll('.event-marker')).toHaveLength(3)
  await wrapper.findAll('button').find(button => button.text()==='Edit')!.trigger('click')
  expect((wrapper.get('input').element as HTMLInputElement).value).toBe(event.summary)
  await wrapper.setProps({ embedded:false })
  expect(wrapper.get('h3').text()).toBe('Timeline')
})
