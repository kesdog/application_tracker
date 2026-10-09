// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ApplicationTable from '../../src/components/applications/ApplicationTable.vue'
import Applications from '../../src/Applications.vue'
import ActiveApplicationFilters from '../../src/components/applications/ActiveApplicationFilters.vue'
import { appliedFilters, blankFilters } from '../../src/applicationFilters'
import { resetTablePreferences, updateTablePreferences } from '../../src/settings/tablePreferences'
import { getDashboard, listApplications, type Application, type DashboardData } from '../../src/api'

vi.mock('../../src/api', async importOriginal => ({ ...await importOriginal<typeof import('../../src/api')>(), listApplications: vi.fn(), getDashboard: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const emptyDashboard: DashboardData = { counts: { active_applications: 0, followups_due: 0, followups_overdue: 0, tasks_due: 0, tasks_overdue: 0, upcoming_interviews: 0 }, upcoming: [], due_followups: [], overdue_followups: [], recent_activity: [] }
const application = (index: number): Application => ({ id: String(index), company: `Company ${String(index).padStart(2, '0')}`, job_title: `Engineer ${index}`, date_applied: `2026-10-${String(index + 1).padStart(2, '0')}`, status: 'SUBMITTED', outcome: null, job_url: null, email_reference: null, phone_number: null, contact_type: 'EMAIL', location: 'Paris', remote_policy: 'HYBRID', contract_type: 'CDI', source: 'OTHER', description: null, requirements: null, posting_status: 'LIVE', posting_last_checked_at: null, posting_http_status: null, posting_final_url: null, posting_check_method: null, posting_check_reason: null, posting_check_failures: 0, followup_delay_days: null, max_followup_suggestions: null, deleted_at: null, duplicate_warnings: [] })
beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  resetTablePreferences()
  Object.assign(appliedFilters, blankFilters())
  window.location.hash = '#/applications'
  vi.mocked(listApplications).mockReset().mockResolvedValue([application(0)])
  vi.mocked(getDashboard).mockReset().mockResolvedValue(emptyDashboard)
})
afterEach(() => { resetTablePreferences(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('sorts the entire result set before pagination and keeps focus links and core columns', async () => {
  updateTablePreferences({ pageSize: 10, columns: [] })
  const wrapper = mount(ApplicationTable, { props: { applications: Array.from({ length: 12 }, (_, i) => application(i)), dashboard: emptyDashboard, overdueIds: new Set<string>(), loading: false, hasFilters: false, error: false }, global })
  expect(wrapper.findAll('tbody tr')).toHaveLength(10)
  expect(wrapper.findAll('tbody a')[0]!.attributes('href')).toBe('#/applications/11')
  expect(wrapper.findAll('thead th').map(cell => cell.text())).toEqual(['Date applied', 'Company', 'Position', 'Status'])
  await wrapper.get('button[aria-label="Next Page"]').trigger('click')
  expect(wrapper.findAll('tbody tr')).toHaveLength(2)
  await wrapper.findAll('thead th')[1]!.trigger('click')
  expect(wrapper.findAll('tbody a')[0]!.attributes('href')).toBe('#/applications/0')
  updateTablePreferences({ columns: ['nextAction'], density: 'comfortable' })
  await flushPromises()
  expect(wrapper.classes()).toContain('density-comfortable')
  expect(wrapper.text()).toContain('Next action')
})

it('preserves active filters on a failed removal and refreshes the applied query on SSE invalidation', async () => {
  Object.assign(appliedFilters, { status: 'INTERVIEW', company: 'Example' })
  const wrapper = mount(Applications, { global })
  await flushPromises()
  vi.mocked(listApplications).mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('button[aria-label="Remove Status: Interview"]').trigger('click')
  await flushPromises()
  expect(wrapper.getComponent(ActiveApplicationFilters).text()).toContain('Status: Interview')
  expect(appliedFilters.status).toBe('INTERVIEW')
  window.dispatchEvent(new Event('tracker:invalidate'))
  await flushPromises()
  expect(listApplications).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'INTERVIEW', company: 'Example' }))
  await wrapper.get('button[aria-label="Remove Status: Interview"]').trigger('click')
  await flushPromises()
  expect(listApplications).toHaveBeenLastCalledWith(expect.objectContaining({ status: '', company: 'Example' }))
  expect(appliedFilters.status).toBe('')
  expect(wrapper.getComponent(ActiveApplicationFilters).text()).not.toContain('Status: Interview')
})

it('ignores an older response after a newer invalidation finishes', async () => {
  let resolveOld!: (value: Application[]) => void
  vi.mocked(listApplications).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
  const wrapper = mount(Applications, { global })
  window.dispatchEvent(new Event('tracker:invalidate'))
  await flushPromises()
  resolveOld([application(1)])
  await flushPromises()
  expect(wrapper.find('a[href="#/applications/0"]').exists()).toBe(true)
  expect(wrapper.find('a[href="#/applications/1"]').exists()).toBe(false)
})
