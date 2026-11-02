// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import AIConnections from '../../src/components/settings/AIConnections.vue'
import * as api from '../../src/aiConnections'
import { ApiRequestError } from '../../src/api'

vi.mock('../../src/aiConnections', () => ({ getAIConnections: vi.fn(), startChatGPT: vi.fn(), connectClaude: vi.fn(), disconnectAI: vi.fn(), getAIModels: vi.fn(), testAI: vi.fn() }))
enableAutoUnmount(afterEach)
const global = { plugins: [[PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]] }
const fresh = (): api.AIConnections => ({ chatgpt: { available: true, connected: false, can_use: false, account: null, email: null, accounts: [] }, claude: { available: true, connected: false, method: 'api_key' } })
const button = (wrapper: VueWrapper, label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => {
  vi.resetAllMocks()
  window.location.hash = '#/settings?tab=connections'
  vi.mocked(api.getAIConnections).mockResolvedValue(fresh())
})

it('loads connection state without generating usage or beginning authorization', async () => {
  const wrapper = mount(AIConnections, { global })
  await flushPromises()
  expect(wrapper.text()).toContain('Continue with ChatGPT')
  expect(wrapper.text()).toContain('Claude subscriptions and API billing are separate')
  expect(api.startChatGPT).not.toHaveBeenCalled()
  expect(api.testAI).not.toHaveBeenCalled()
  expect(api.getAIModels).not.toHaveBeenCalled()
})

it('clears a submitted API key after failure and success and preserves connection feedback', async () => {
  const wrapper = mount(AIConnections, { global, attachTo: document.body })
  await flushPromises()
  const input = wrapper.get('input[type=password]')
  await input.setValue('private-key-fixture')
  vi.mocked(api.connectClaude).mockRejectedValueOnce(new Error('Claude key not accepted'))
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.connectClaude).toHaveBeenCalledWith('private-key-fixture')
  expect((input.element as HTMLInputElement).value).toBe('')
  expect(wrapper.get('[role=alert]').text()).toContain('Claude key not accepted')
  expect(document.activeElement).toBe(wrapper.get('[role=alert]').element)
  const connected = fresh(); connected.claude.connected = true
  vi.mocked(api.connectClaude).mockResolvedValue(connected)
  await input.setValue('replacement-key-fixture')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect((input.element as HTMLInputElement).value).toBe('')
  expect(wrapper.text()).toContain('API key connected')
  expect(wrapper.text()).not.toContain('replacement-key-fixture')
  vi.mocked(api.disconnectAI).mockResolvedValue({ connections: fresh(), message: 'Claude API key removed.' })
  await button(wrapper, 'Disconnect Claude').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('Claude API key removed.')
})

it('uses account-specific models and displays usage errors without erasing the connection', async () => {
  const connected = fresh()
  Object.assign(connected.chatgpt, { connected: true, can_use: true, account: 'issued-app', email: 'owner@example.test', accounts: [{ id: 'issued-app', label: 'Owner account', connected: true }] })
  vi.mocked(api.getAIConnections).mockResolvedValue(connected)
  vi.mocked(api.getAIModels).mockResolvedValue([{ id: 'allowed-model', name: 'Allowed model' }])
  const wrapper = mount(AIConnections, { global }); await flushPromises()
  expect(wrapper.text()).toContain('owner@example.test')
  await button(wrapper, 'Refresh ChatGPT models').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('Allowed model')
  expect(api.testAI).not.toHaveBeenCalled()
  vi.mocked(api.testAI).mockRejectedValue(new ApiRequestError('ChatGPT usage limit reached. Review app allowance.', 'usage_limit', 120))
  await button(wrapper, 'Test ChatGPT AI access').trigger('click'); await flushPromises()
  expect(api.testAI).toHaveBeenCalledWith('chatgpt', 'allowed-model')
  expect(wrapper.get('[role=alert]').text()).toContain('usage limit reached')
  expect(wrapper.get('[role=alert]').text()).toContain('120 seconds')
  expect(wrapper.text()).toContain('Linked · owner@example.test')
  expect(wrapper.find('a[href="https://chatgpt.com/settings/usage"]').exists()).toBe(true)
  vi.mocked(api.startChatGPT).mockRejectedValue(new Error('Connection unavailable'))
  await button(wrapper, 'Continue with ChatGPT').trigger('click'); await flushPromises()
  expect(api.startChatGPT).toHaveBeenCalledWith('issued-app')
})

it('offers connector setup on hosted installs and handles callback cancellation without changing the link state', async () => {
  const hosted = fresh(); hosted.chatgpt.available = false
  vi.mocked(api.getAIConnections).mockResolvedValue(hosted)
  window.location.hash = '#/settings?tab=connections&provider=chatgpt&ai_result=permission'
  const wrapper = mount(AIConnections, { global }); await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('cancelled')
  expect(wrapper.text()).toContain('ChatGPT connector setup')
  expect(wrapper.findAll('button').some(item => item.text() === 'Continue with ChatGPT')).toBe(false)
  expect(window.location.hash).not.toContain('ai_result')
  await wrapper.get('a[href="#/settings?tab=agent&provider=claude"]').trigger('click')
  expect(wrapper.emitted('connector')).toEqual([['claude']])
})
