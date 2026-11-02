// @vitest-environment jsdom
import '../support/browser'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import Dashboard from '../../src/Dashboard.vue'
import Tasks from '../../src/Tasks.vue'
import Interviews from '../../src/Interviews.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getDashboard: vi.fn(), listTasks: vi.fn(), updateTask: vi.fn(), listInterviews: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const application = { id: 'app-1', company: 'Example', job_title: 'Engineer' }
beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.unstubAllGlobals())
function tab(wrapper: ReturnType<typeof mount>, label: string) { return wrapper.findAll('[role=tab]').find(item => item.text().startsWith(label))! }

it('keeps the dashboard focused on upcoming work and reveals activity in one click', async () => {
  vi.mocked(api.getDashboard).mockResolvedValue({ counts: { active_applications: 2, tasks_due: 1, tasks_overdue: 2, followups_due: 3, followups_overdue: 1, upcoming_interviews: 1 }, upcoming: [], due_followups: [], overdue_followups: [], recent_activity: [{ id: 'event-1', summary: 'Application updated', application, created_at: '2026-10-01T12:00:00Z', actor_type: 'USER' }] } as unknown as api.DashboardData)
  const wrapper = mount(Dashboard, { global })
  await flushPromises()
  expect(wrapper.findAll('.metric')).toHaveLength(4)
  expect(wrapper.findAll('.metric')[1]!.text()).toContain('3')
  expect(wrapper.get('.recent-panel').isVisible()).toBe(false)
  await tab(wrapper, 'Activity').trigger('click')
  expect(wrapper.get('.recent-panel').isVisible()).toBe(true)
  expect(wrapper.get('.followups-panel').isVisible()).toBe(false)
  expect(wrapper.get('.recent-panel a').attributes('href')).toBe('#/applications/app-1')
})

it('moves completed tasks to history and exposes reopening without mixing the two lists', async () => {
  const task = { id: 'task-1', application_id: application.id, application, title: 'Prepare interview', status: 'PENDING', due_at: null, description: 'Read the role' } as api.TaskListItem
  vi.mocked(api.listTasks).mockResolvedValue([task])
  vi.mocked(api.updateTask).mockResolvedValue({ ...task, status: 'COMPLETED' })
  const wrapper = mount(Tasks, { global })
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === 'Complete')!.trigger('click')
  await flushPromises()
  expect(wrapper.findAll('.task-row').filter(row => row.isVisible())).toHaveLength(0)
  await tab(wrapper, 'History').trigger('click')
  expect(wrapper.findAll('.task-row').filter(row => row.isVisible())).toHaveLength(1)
  expect(wrapper.findAll('button').find(button => button.text() === 'Reopen')!.isVisible()).toBe(true)
  expect(api.updateTask).toHaveBeenCalledWith(application.id, task.id, { status: 'COMPLETED' })
})

it('separates past interviews from upcoming conversations while keeping meeting links visible', async () => {
  const base = { application, application_id: application.id, type: 'TECHNICAL', duration: 30, interviewer: 'Alex', location: 'Online' }
  vi.mocked(api.listInterviews).mockResolvedValue([{ ...base, id: 'future', scheduled_at: '2099-10-01T10:00:00Z', meeting_url: 'https://example.com/meeting' }, { ...base, id: 'past', scheduled_at: '2020-10-01T10:00:00Z', result: 'Conversation recorded' }] as api.InterviewListItem[])
  const wrapper = mount(Interviews, { global })
  await flushPromises()
  expect(wrapper.get('a[href="https://example.com/meeting"]').isVisible()).toBe(true)
  expect(wrapper.findAll('.work-card').filter(card => card.isVisible())).toHaveLength(1)
  await tab(wrapper, 'Previous').trigger('click')
  expect(wrapper.get('a[href="https://example.com/meeting"]').isVisible()).toBe(false)
  expect(wrapper.findAll('.work-card').filter(card => card.isVisible())[0]!.text()).toContain('Conversation recorded')
})
