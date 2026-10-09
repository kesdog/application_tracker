// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import Root from '../../src/Root.vue'
import { checkHumanSession, humanSession, withSessionHeaders } from '../../src/auth'
import { updateFollowUp, listApplications } from '../../src/api'

enableAutoUnmount(afterEach)
beforeEach(() => {
  Object.assign(humanSession, { enabled: false, authenticated: false, checking: true, loaded: false, csrf: '', error: '' })
  window.location.hash = '#/followups/job-1/message-1'
  localStorage.clear()
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
const global = { stubs: { App: { template: '<div>Workspace content<button @click="$emit(\'signout\')">Sign out</button></div>' } } }
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

it('holds private workspace components until the session check succeeds', async () => {
  let resolve!: (value: Response) => void
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise<Response>(done => { resolve = done })))
  const wrapper = mount(Root, { global })
  expect(wrapper.text()).toContain('Connecting')
  expect(wrapper.text()).not.toContain('Workspace content')
  resolve(reply({ enabled: true, authenticated: false, csrf_token: null }))
  await flushPromises()
  expect(wrapper.find('input[type="password"]').exists()).toBe(true)
  expect(wrapper.text()).not.toContain('Workspace content')
})

it('signs in without changing the deep link or storing credentials in local storage', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(reply({ enabled: true, authenticated: false, csrf_token: null })).mockResolvedValueOnce(reply({ enabled: true, authenticated: true, csrf_token: 'csrf-1' }))
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(Root, { global })
  await flushPromises()
  await wrapper.get('input[type="password"]').setValue('fixture password only')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('Workspace content')
  expect(window.location.hash).toBe('#/followups/job-1/message-1')
  expect(localStorage.length).toBe(0)
  expect(fetch).toHaveBeenLastCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: JSON.stringify({ password: 'fixture password only' }) }))
})

it('keeps login errors visible without opening the workspace', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(reply({ enabled: true, authenticated: false, csrf_token: null })).mockResolvedValueOnce(reply({ detail: 'Incorrect workspace password' }, 401)))
  const wrapper = mount(Root, { global })
  await flushPromises()
  await wrapper.get('input[type="password"]').setValue('wrong')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('Incorrect workspace password')
  expect(wrapper.text()).not.toContain('Workspace content')
})

it('cannot unlock the workspace from a malformed session response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ authenticated: true })))
  await checkHumanSession()
  expect(humanSession.loaded).toBe(false)
  expect(humanSession.authenticated).toBe(false)
})

it('adds the current CSRF token to writes and leaves multipart content type alone', async () => {
  Object.assign(humanSession, { enabled: true, authenticated: true, csrf: 'security-token' })
  const fetch = vi.fn().mockResolvedValue(reply({}))
  vi.stubGlobal('fetch', fetch)
  await updateFollowUp('job', 'message', { body: 'Edited', expected_revision: 4 })
  const options = fetch.mock.calls[0]![1] as RequestInit
  expect(new Headers(options.headers).get('X-CSRF-Token')).toBe('security-token')
  expect(new Headers(options.headers).get('Content-Type')).toBe('application/json')
  const multipart = withSessionHeaders({ method: 'POST', body: new FormData() })
  expect(new Headers(multipart.headers).get('Content-Type')).toBeNull()
  expect(withSessionHeaders({ method: 'GET' }).headers).toBeUndefined()
})

it('removes private UI on a rejected session and clears it after confirmed sign-out', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(reply({ enabled: true, authenticated: true, csrf_token: 'csrf-1' })).mockResolvedValueOnce(reply({ authenticated: false }))
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(Root, { global })
  await flushPromises()
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain('Workspace content')
  Object.assign(humanSession, { enabled: true, authenticated: true, csrf: 'csrf-2' })
  fetch.mockResolvedValueOnce(reply({ detail: 'Sign in' }, 401))
  await expect(listApplications()).rejects.toThrow('Sign in')
  expect(humanSession.authenticated).toBe(false)
  expect(humanSession.csrf).toBe('')
})
