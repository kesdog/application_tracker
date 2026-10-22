// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import App from '../../src/App.vue'
import Drawer from 'primevue/drawer'
import * as api from '../../src/api'
import { loadAppearance, themeMode } from '../../src/settings/appearanceStore'
import { navigationSaveError, sidebarCollapsed, sidebarStorageKey } from '../../src/settings/navigationPreferences'

vi.mock('../../src/Dashboard.vue', () => ({ __esModule: true, default: { template: '<p>Dashboard content</p>' } }))
vi.mock('../../src/Applications.vue', () => ({ __esModule: true, default: { template: '<p>Application content</p>' } }))
vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getApplication: vi.fn() }))
enableAutoUnmount(afterEach)
beforeEach(() => {
  localStorage.clear(); loadAppearance(); sidebarCollapsed.value = false; navigationSaveError.value = ''
  window.location.hash = '#/dashboard'
  vi.stubGlobal('EventSource', class { addEventListener() {} close() {} })
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} })))
})
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); loadAppearance(); sidebarCollapsed.value = false })
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]], stubs: { ConfirmDialog: true } }

it('collapses to an accessible icon rail, persists the choice and expands again', async () => {
  const wrapper = mount(App, { global })
  await flushPromises()
  await wrapper.get('button[aria-label="Collapse sidebar"]').trigger('click')
  expect(wrapper.get('.shell').classes()).toContain('sidebar-collapsed')
  expect(wrapper.get('button[aria-label="Expand sidebar"]').attributes('aria-expanded')).toBe('false')
  expect(wrapper.get('button[aria-label="Expand sidebar"]').attributes('aria-controls')).toBe('workspace-sidebar')
  expect(JSON.parse(localStorage.getItem(sidebarStorageKey)!)).toBe(true)
  for (const name of ['Dashboard', 'All applications', 'Add application', 'Interviews', 'Tasks', 'Export', 'Settings']) {
    const link = wrapper.get(`a[aria-label="${name}"]`)
    expect(link.attributes('title')).toBe(name)
    expect(link.attributes('href')).toMatch(/^#\//)
  }
  await wrapper.get('button[aria-label="Expand sidebar"]').trigger('click')
  expect(wrapper.get('.shell').classes()).not.toContain('sidebar-collapsed')
})

it('uses a closed left drawer on mobile and closes it after navigation', async () => {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(query => ({ matches: query === '(max-width: 760px)', media: query, addEventListener() {}, removeEventListener() {} })))
  const wrapper = mount(App, { global, attachTo: document.body })
  await flushPromises()
  expect(document.querySelector('#workspace-sidebar')).toBeNull()
  await wrapper.get('button[aria-label="Open navigation"]').trigger('click')
  await flushPromises()
  expect(wrapper.getComponent(Drawer).props('position')).toBe('left')
  expect(document.querySelector('#workspace-sidebar a[aria-label="All applications"] .pi-briefcase')).not.toBeNull()
  ;(document.querySelector('#workspace-sidebar a[aria-label="All applications"]') as HTMLElement).click()
  await flushPromises()
  expect(wrapper.get('button[aria-label="Open navigation"]').attributes('aria-expanded')).toBe('false')
})

it('includes the current company in breadcrumbs and clears it on other pages', async () => {
  window.location.hash = '#/applications/job-1'
  vi.mocked(api.getApplication).mockResolvedValue({ company: 'Example Ltd' } as api.Application)
  const wrapper = mount(App, { global })
  await flushPromises()
  expect(wrapper.get('nav[aria-label="Breadcrumb"]').text()).toContain('Example Ltd')
  expect(wrapper.get('.current-company').attributes('aria-current')).toBe('page')
  window.location.hash = '#/dashboard'
  window.dispatchEvent(new Event('hashchange'))
  await flushPromises()
  expect(wrapper.find('.current-company').exists()).toBe(false)
  expect(wrapper.findAll('.primary-nav a[href="#/applications"]')).toHaveLength(1)
})

it('toggles both directions through the labeled switch and keeps the current route', async () => {
  const wrapper = mount(App, { global })
  await flushPromises()
  await wrapper.get('input#workspace-theme').setValue(true)
  expect(themeMode.value).toBe('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(wrapper.text()).toContain('Dark · Midnight')
  expect(window.location.hash).toBe('#/dashboard')
  await wrapper.get('input#workspace-theme').setValue(false)
  expect(themeMode.value).toBe('light')
  expect(wrapper.text()).toContain('Light · Paper')
})

it('offers the welcome guide and legal documents from the footer', async () => {
  const wrapper = mount(App, { global })
  await flushPromises()
  const help = wrapper.get('nav[aria-label="Help and legal"]')
  const buttons = help.findAll('button')
  for (const button of buttons) await button.trigger('click')
  expect(wrapper.emitted('openGuide')).toEqual([[]])
  expect(wrapper.emitted('openLegal')).toEqual([['terms'], ['privacy']])
})
