// @vitest-environment jsdom
import '../support/browser'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import AgentSettings from '../../src/AgentSettings.vue'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getAgentSettings: vi.fn(), getIntegrationStatus: vi.fn(), getAgentConnectionInfo: vi.fn(), getHealth: vi.fn(), saveAgentPermissions: vi.fn(), regenerateAgentToken: vi.fn() }))
enableAutoUnmount(afterEach)
beforeEach(() => {
  window.location.hash = '#/settings'
  vi.mocked(api.getAgentSettings).mockResolvedValue({ configured: true, permissions: { read: true, create: false, edit: false, draft: false, tasks: false, interviews: false } } as api.AgentSettings)
  vi.mocked(api.getHealth).mockResolvedValue({ version: 'test' } as api.Health)
  vi.mocked(api.getIntegrationStatus).mockResolvedValue({ mail: { connected: false }, calendar: { connected: false } } as api.IntegrationStatus)
  vi.mocked(api.getAgentConnectionInfo).mockResolvedValue({} as api.AgentConnectionInfo)
  vi.clearAllMocks()
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]], stubs: { MailSyncSettings: { template: '<div>Mail scan limit</div>' }, AppearanceSettings: { template: '<div>Theme preferences</div>' }, FollowUpSettings: { template: '<input aria-label="Default message" />' }, WorkspaceData: { template: '<div>Restore records</div>' }, GoogleSettings: { template: '<div>Connection choices</div>' }, PhoneSetup: true, PhoneInstallation: true, PhoneNotifications: { template: '<div>Phone notices</div>' } } }

it('shows one settings category at a time and preserves an edited template across category changes', async () => {
  const wrapper = mount(AgentSettings, { global })
  await flushPromises()
  const panels = wrapper.findAll('[role=tabpanel]')
  expect(panels.filter(panel => panel.isVisible())).toHaveLength(1)
  expect(panels[0]!.text()).toContain('Theme preferences')
  const tabs = wrapper.findAll('[role=tab]')
  for (const tab of tabs) {
    await tab.trigger('click')
    expect(panels.filter(panel => panel.isVisible())).toHaveLength(1)
  }
  await tabs[1]!.trigger('click')
  await wrapper.get('[aria-label="Default message"]').setValue('Unfinished template')
  await tabs[4]!.trigger('click')
  expect(wrapper.get('[aria-label="Default message"]').isVisible()).toBe(false)
  await tabs[1]!.trigger('click')
  expect((wrapper.get('[aria-label="Default message"]').element as HTMLInputElement).value).toBe('Unfinished template')
  expect(api.regenerateAgentToken).not.toHaveBeenCalled()
  expect(api.saveAgentPermissions).not.toHaveBeenCalled()
})

it('opens contextual sync and data links directly, including while Settings is already mounted', async () => {
  window.location.hash = '#/settings?tab=connections'
  const wrapper = mount(AgentSettings, { global })
  await flushPromises()
  expect(wrapper.get('[role=tab][aria-selected=true]').text()).toBe('Connections')
  expect(wrapper.get('[role=tabpanel][data-p-active=true]').text()).toContain('Mail scan limit')
  window.location.hash = '#/settings?tab=data'
  window.dispatchEvent(new Event('hashchange'))
  await flushPromises()
  expect(wrapper.get('[role=tab][aria-selected=true]').text()).toBe('Data & recovery')
})
