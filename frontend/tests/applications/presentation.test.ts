// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import type { Application, DashboardData, UpcomingItem } from '../../src/api'
import ApplicationStatusTag from '../../src/components/applications/ApplicationStatusTag.vue'
import ApplicationOutcomeTag from '../../src/components/applications/ApplicationOutcomeTag.vue'
import ApplicationNextAction from '../../src/components/applications/ApplicationNextAction.vue'
import ActiveApplicationFilters from '../../src/components/applications/ActiveApplicationFilters.vue'
import { applicationOutcomeMeta, applicationRowClass, applicationStatusMeta } from '../../src/presentation/applicationPresentation'
import { nextApplicationAction } from '../../src/presentation/nextAction'
import { resetAppearance } from '../../src/settings/appearanceStore'

enableAutoUnmount(afterEach)
afterEach(resetAppearance)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const now = Date.parse('2026-10-07T12:00:00Z')
const item = (kind: UpcomingItem['kind'], due_at: string, applicationId = 'app'): UpcomingItem => ({ id: kind + due_at, kind, title: `${kind} title`, due_at, status: 'PENDING', application: { id: applicationId, job_title: 'Engineer', company: 'Example' } })
const dashboard = (): DashboardData => ({ counts: { active_applications: 1, followups_due: 0, followups_overdue: 0, tasks_due: 0, tasks_overdue: 0, upcoming_interviews: 0 }, upcoming: [], due_followups: [], overdue_followups: [], recent_activity: [] })

it.each(Object.entries(applicationStatusMeta))('renders %s with a readable label, icon and settings color', (status, meta) => {
  const wrapper = mount(ApplicationStatusTag, { props: { status: status as Application['status'] }, global })
  expect(wrapper.text()).toBe(meta.label)
  expect(wrapper.find('span.pi').classes()).toContain(meta.icon!.split(' ')[1])
  expect(wrapper.attributes('style')).toContain('--at-')
})

it.each(Object.entries(applicationOutcomeMeta))('renders the %s outcome label', (outcome, meta) => {
  const wrapper = mount(ApplicationOutcomeTag, { props: { outcome: outcome as Application['outcome'] }, global })
  expect(wrapper.text()).toBe(meta.label)
})

it('shows explicit empty outcome and action states', () => {
  expect(mount(ApplicationOutcomeTag, { props: { outcome: null }, global }).attributes('aria-label')).toBe('No outcome')
  expect(mount(ApplicationNextAction, { props: { action: null } }).attributes('aria-label')).toBe('No upcoming action')
})

it('prioritizes overdue follow-ups, future interviews, due follow-ups, then tasks for this application', () => {
  const summary = dashboard()
  summary.upcoming = [item('TASK', '2026-10-08T10:00:00Z'), item('INTERVIEW', '2026-10-09T10:00:00Z'), item('INTERVIEW', '2026-10-07T10:00:00Z')]
  summary.due_followups = [item('FOLLOWUP', '2026-10-07T13:00:00Z')]
  summary.overdue_followups = [item('FOLLOWUP', '2026-10-05T10:00:00Z'), item('FOLLOWUP', '2026-10-01T10:00:00Z', 'other')]
  expect(nextApplicationAction('app', summary, now)?.label).toBe('Overdue follow-up')
  summary.overdue_followups = []
  expect(nextApplicationAction('app', summary, now)?.dueAt).toBe('2026-10-09T10:00:00Z')
  summary.upcoming = summary.upcoming.filter(entry => entry.kind === 'TASK')
  expect(nextApplicationAction('app', summary, now)?.label).toBe('Follow-up')
  summary.due_followups = []
  expect(nextApplicationAction('app', summary, now)?.label).toBe('Pending task')
  expect(nextApplicationAction('missing', summary, now)).toBeNull()
  expect(nextApplicationAction('app', null, now)).toBeNull()
})

it('shows urgency text and a timestamp, and gives overdue rows priority over closed rows', () => {
  const summary = dashboard()
  summary.overdue_followups = [item('FOLLOWUP', '2026-10-05T10:00:00Z')]
  const wrapper = mount(ApplicationNextAction, { props: { action: nextApplicationAction('app', summary, now) } })
  expect(wrapper.text()).toContain('Overdue follow-up')
  expect(wrapper.attributes('title')).toContain('FOLLOWUP title')
  const application = { id: 'app', status: 'CLOSED' } as Application
  expect(applicationRowClass(application, new Set(['app']))).toBe('row-overdue')
  expect(applicationRowClass(application, new Set())).toBe('row-closed')
})

it('removes only the selected filter and keeps its chip until the backend accepts removal', async () => {
  const wrapper = mount(ActiveApplicationFilters, { props: { filters: { status: 'INTERVIEW', company: 'Example' }, loading: false }, global })
  await wrapper.get('button[aria-label="Remove Status: Interview"]').trigger('click')
  expect(wrapper.emitted('remove')).toEqual([['status']])
  expect(wrapper.text()).toContain('Status: Interview')
  await wrapper.setProps({ loading: true })
  expect(wrapper.get('button[aria-label="Remove Company: Example"]').attributes('disabled')).toBeDefined()
  await wrapper.setProps({ loading: false, filters: { company: 'Example' } })
  expect(wrapper.text()).not.toContain('Status: Interview')
  expect(wrapper.text()).toContain('Company: Example')
  await wrapper.findAll('button').find(button => button.text() === 'Clear all')!.trigger('click')
  expect(wrapper.emitted('clear')).toHaveLength(1)
})
