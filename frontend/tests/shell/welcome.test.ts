// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import WelcomeExperience from '../../src/components/welcome/WelcomeExperience.vue'
import Root from '../../src/Root.vue'
import { humanSession } from '../../src/auth'
import { loadAppearance, themeMode } from '../../src/settings/appearanceStore'

enableAutoUnmount(afterEach)
const guideKey = 'application-tracker:welcome:v1'
const noticeKey = 'application-tracker:storage-notice:v1'
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]], stubs: { teleport: true } }
const button = (wrapper: VueWrapper, text: string) => {
  const match = wrapper.findAll('button').find(item => item.text() === text)
  if (!match) throw new Error(`Missing button: ${text}`)
  return match
}
beforeEach(() => {
  localStorage.clear(); loadAppearance()
  window.location.hash = '#/followups/job-1/message-1'
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('finishes all three steps without sign-in, preserves a deep link and remembers completion separately from the notice', async () => {
  const wrapper = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  expect(wrapper.get('[role="dialog"]').text()).toContain('Start without an account connection')
  expect(wrapper.get('[aria-current="step"]').text()).toContain('Welcome')
  await button(wrapper, 'Next').trigger('click')
  expect(wrapper.text()).toContain('Review every follow-up')
  await button(wrapper, 'Back').trigger('click')
  expect(wrapper.text()).toContain('A calmer place')
  await button(wrapper, 'Next').trigger('click')
  await button(wrapper, 'Next').trigger('click')
  await wrapper.get('input[value="dark"]').setValue()
  expect(themeMode.value).toBe('dark')
  await button(wrapper, 'Start tracking').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(JSON.parse(localStorage.getItem(guideKey)!)).toBe(true)
  expect(localStorage.getItem(noticeKey)).toBeNull()
  expect(window.location.hash).toBe('#/followups/job-1/message-1')
  expect(fetch).not.toHaveBeenCalled()
  await button(wrapper, 'Got it').trigger('click')
  expect(JSON.parse(localStorage.getItem(noticeKey)!)).toBe(true)
  wrapper.unmount()
  const returning = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  expect(returning.find('[role="dialog"]').exists()).toBe(false)
  expect(returning.find('.storage-notice').exists()).toBe(false)
})

it('skips, reopens and closes with the dialog close button without changing the route', async () => {
  const wrapper = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  await button(wrapper, 'Skip for now').trigger('click')
  await flushPromises()
  expect(localStorage.getItem(guideKey)).toBe('true')
  wrapper.vm.openGuide()
  await flushPromises()
  await wrapper.get('button[aria-label="Close"]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(window.location.hash).toBe('#/followups/job-1/message-1')
})

it('returns from legal details to the same guide step without recording agreement', async () => {
  const wrapper = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  await button(wrapper, 'Next').trigger('click')
  await button(wrapper, 'Terms and conditions').trigger('click')
  expect(wrapper.text()).toContain('Your records and responsibilities')
  expect(localStorage.getItem(guideKey)).toBeNull()
  expect(localStorage.getItem(noticeKey)).toBeNull()
  await button(wrapper, 'Back to guide').trigger('click')
  expect(wrapper.get('[aria-current="step"]').text()).toContain('How it works')
  await wrapper.setProps({ ready: false })
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(localStorage.getItem(guideKey)).toBeNull()
})

it('shows public legal information before login and defers onboarding until access is available', async () => {
  const wrapper = mount(WelcomeExperience, { props: { ready: false }, global })
  await button(wrapper, 'Privacy & cookies').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('__Host-tracker-session')
  expect(wrapper.text()).toContain('does not grant marketing consent')
  await wrapper.setProps({ ready: true })
  await button(wrapper, 'Close').trigger('click')
  expect(wrapper.text()).toContain('A calmer place')
})

it('opens connection settings only on explicit request and never starts Google authorization', async () => {
  const wrapper = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  await button(wrapper, 'Next').trigger('click')
  await button(wrapper, 'Next').trigger('click')
  await button(wrapper, 'Explore optional connections').trigger('click')
  expect(window.location.hash).toBe('#/settings')
  expect(fetch).not.toHaveBeenCalled()
  expect(localStorage.getItem(guideKey)).toBe('true')
})

it('handles malformed or blocked storage without preventing use', async () => {
  localStorage.setItem(guideKey, '{broken')
  localStorage.setItem(noticeKey, '"true"')
  const wrapper = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage blocked') })
  await button(wrapper, 'Skip for now').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(wrapper.get('[role="status"]').text()).toContain('You can continue')
  await button(wrapper, 'Got it').trigger('click')
  expect(wrapper.find('.storage-notice').exists()).toBe(false)
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage blocked') })
  const blocked = mount(WelcomeExperience, { props: { ready: true }, global })
  await flushPromises()
  expect(blocked.find('[role="dialog"]').exists()).toBe(true)
})

it('integrates with a local workspace without login and wires footer help actions', async () => {
  Object.assign(humanSession, { enabled: false, authenticated: false, checking: true, loaded: false, csrf: '', error: '' })
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ enabled: false, authenticated: true, csrf_token: null }), { status: 200 }))
  const wrapper = mount(Root, { global: { ...global, stubs: { ...global.stubs, App: { template: '<div>Local workspace<button @click="$emit(\'open-guide\')">Reopen guide</button><button @click="$emit(\'open-legal\', \'terms\')">Read terms</button></div>' } } } })
  await flushPromises()
  expect(wrapper.text()).toContain('Local workspace')
  expect(wrapper.text()).toContain('A calmer place')
  expect(wrapper.find('input[type="password"]').exists()).toBe(false)
  await button(wrapper, 'Skip for now').trigger('click')
  await button(wrapper, 'Reopen guide').trigger('click')
  expect(wrapper.text()).toContain('A calmer place')
  await button(wrapper, 'Skip for now').trigger('click')
  await button(wrapper, 'Read terms').trigger('click')
  expect(wrapper.text()).toContain('Your records and responsibilities')
  expect(fetch).toHaveBeenCalledTimes(1)
})
