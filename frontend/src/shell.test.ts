// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import App from './App.vue'
import { loadAppearance, themeMode } from './settings/appearanceStore'
import { navigationSaveError, sidebarCollapsed, sidebarStorageKey } from './settings/navigationPreferences'

vi.mock('./Dashboard.vue', () => ({ __esModule: true, default: { template: '<p>Dashboard content</p>' } }))
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
  for (const name of ['Dashboard', 'Applications', 'All applications', 'Add application', 'Interviews', 'Tasks', 'Export', 'Settings']) {
    const link = wrapper.get(`a[aria-label="${name}"]`)
    expect(link.attributes('title')).toBe(name)
    expect(link.attributes('href')).toMatch(/^#\//)
  }
  await wrapper.get('button[aria-label="Expand sidebar"]').trigger('click')
  expect(wrapper.get('.shell').classes()).not.toContain('sidebar-collapsed')
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
