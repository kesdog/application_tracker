// @vitest-environment jsdom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import PhoneApp from '../../src/phone/PhoneApp.vue'
import { IndexedReplicaStore } from '../../src/phone/core/storage'
import type { RecordState } from '../../src/phone/core/storage'
import { fixture } from './support'
const model = vi.hoisted(() => ({ paired: true, unlocked: false, rows: [] as RecordState[], connected: false,
  auth: { connect: vi.fn(), clear: vi.fn(), identity: vi.fn() },
  engine: { status: vi.fn(), records: vi.fn(), pair: vi.fn(), unlock: vi.fn(), edit: vi.fn(), lock: vi.fn(), sync: vi.fn(), syncing: false, get unlocked() { return model.unlocked } },
}))
vi.mock('../../src/phone/runtime', () => ({ createRuntime: () => ({ auth: model.auth, engine: model.engine, preload: async () => {} }) }))
vi.mock('../../src/phone/core/auth', async original => ({ ...await original<typeof import('../../src/phone/core/auth')>(), loadGoogleOAuth: vi.fn().mockResolvedValue({}) }))
enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.clearAllMocks(); model.paired = true; model.unlocked = false; model.rows = []; model.connected = false
  vi.stubGlobal('isSecureContext', true); vi.stubGlobal('indexedDB', {})
  vi.spyOn(IndexedReplicaStore.prototype, 'metadata').mockResolvedValue({ clientId: 'phone.apps.googleusercontent.com', subject: fixture.crypto.subject, email: 'synthetic@example.invalid' } as any)
  vi.spyOn(IndexedReplicaStore.prototype, 'close').mockImplementation(() => {})
  model.engine.status.mockImplementation(async () => ({ paired: model.paired, unlocked: model.unlocked, pending: model.unlocked ? 0 : null, conflicts: model.rows.filter(row => row.reason).length, error: null, lastSuccess: null }))
  model.engine.records.mockImplementation(async () => model.rows)
  model.engine.unlock.mockImplementation(async () => { model.unlocked = true })
  model.engine.lock.mockImplementation(() => { model.unlocked = false })
  model.engine.pair.mockImplementation(async () => { model.paired = true; model.unlocked = true })
  model.auth.identity.mockImplementation(() => model.connected ? { subject: fixture.crypto.subject, email: 'synthetic@example.invalid' } : undefined)
  model.auth.connect.mockImplementation(async () => { model.connected = true; return model.auth.identity() })
  model.auth.clear.mockImplementation(() => { model.connected = false })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(item => item.text().includes(text))! }
function application(reason: string | null = null): RecordState {
  const result = fixture.cases.find((sample: any) => sample.name === (reason ? 'competing' : 'root')).expected
  return { ...result, candidate: result.state, appliedHeads: [fixture.crypto.batch.mutations[0].event_id], id: 'application:' + fixture.crypto.batch.mutations[0].entity_id, entity: 'application', entityId: fixture.crypto.batch.mutations[0].entity_id, reason }
}

it('unlocks cached records without Google and clears sensitive views on lock', async () => {
  model.rows = [application()]
  const wrapper = mount(PhoneApp); await flushPromises()
  expect(wrapper.text()).toContain('Unlock offline')
  await wrapper.get('input[autocomplete=current-password]').setValue('synthetic unlock passphrase')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(model.auth.connect).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('Équipe')
  expect(wrapper.find('input[autocomplete=current-password]').exists()).toBe(false)
  await button(wrapper, 'Lock').trigger('click'); await flushPromises()
  expect(wrapper.text()).not.toContain('Équipe'); expect(model.auth.clear).toHaveBeenCalled()
})

it('edits a reactive record with its reviewed heads and queues a local save', async () => {
  model.rows = [application()]; model.unlocked = true
  const wrapper = mount(PhoneApp); await flushPromises()
  await button(wrapper, 'Edit application').trigger('click'); await flushPromises()
  const field = wrapper.findAll('label').find(item => item.text() === 'Company')!.get('input')
  await field.setValue('Edited from phone form')
  await wrapper.get('.editor').trigger('submit'); await flushPromises()
  expect(model.engine.edit).toHaveBeenCalledWith('application', model.rows[0]!.entityId, expect.objectContaining({ company: 'Edited from phone form' }), model.rows[0]!.heads)
  expect(wrapper.text()).toContain('Saved on this phone')
})

it('preserves reviewed conflict choices on refresh and invalidates confirmation after changes', async () => {
  model.rows = [application('competing_values')]; model.unlocked = true
  const wrapper = mount(PhoneApp); await flushPromises()
  const select = wrapper.get('.conflict select'), options = select.findAll('option')
  await select.setValue(options[options.length - 1]!.attributes('value'))
  await wrapper.get('.conflict input[type=checkbox]').setValue(true)
  await button(wrapper, 'Refresh local view').trigger('click'); await flushPromises()
  expect((wrapper.get('.conflict input[type=checkbox]').element as HTMLInputElement).checked).toBe(true)
  await wrapper.get('.conflict select').setValue(options[0]!.attributes('value'))
  expect(button(wrapper, 'Save reviewed resolution').attributes('disabled')).toBeDefined()
})

it('rejects mismatching passphrases before enrolling and clears both secret inputs', async () => {
  model.paired = false
  vi.spyOn(IndexedReplicaStore.prototype, 'metadata').mockResolvedValue(undefined)
  const wrapper = mount(PhoneApp); await flushPromises()
  await wrapper.findAll('input')[0]!.setValue('phone.apps.googleusercontent.com')
  await button(wrapper, 'Connect Google for sync').trigger('click'); await flushPromises()
  const secrets = wrapper.findAll('input[type=password]')
  await secrets[0]!.setValue(fixture.crypto.recovery); await secrets[1]!.setValue('first synthetic phrase'); await secrets[2]!.setValue('different synthetic phrase')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(model.engine.pair).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('do not match')
  expect((secrets[1]!.element as HTMLInputElement).value).toBe(''); expect((secrets[2]!.element as HTMLInputElement).value).toBe('')
})

it('shows an explicit HTTPS requirement instead of opening a broken pairing flow', async () => {
  vi.stubGlobal('isSecureContext', false)
  const wrapper = mount(PhoneApp); await flushPromises()
  expect(wrapper.text()).toContain('needs HTTPS'); expect(wrapper.find('form').exists()).toBe(false)
})

it('a scanned QR connects, enrolls and downloads from one submit without key entry', async () => {
  model.paired = false
  vi.spyOn(IndexedReplicaStore.prototype, 'metadata').mockResolvedValue(undefined)
  const wrapper = mount(PhoneApp, { props: { takeHandoff: () => ({ recovery: fixture.crypto.recovery, email: 'synthetic@example.invalid' }) } }); await flushPromises()
  expect(wrapper.text()).not.toContain('Desktop recovery export')
  expect(wrapper.text()).not.toContain('Phone Web OAuth public client ID')
  const secrets = wrapper.findAll('input[type=password]')
  await secrets[0]!.setValue('only a synthetic passphrase'); await secrets[1]!.setValue('only a synthetic passphrase')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(model.auth.connect).toHaveBeenCalledWith({ prompt: '', loginHint: 'synthetic@example.invalid' })
  expect(model.engine.pair).toHaveBeenCalledWith(fixture.crypto.recovery, 'only a synthetic passphrase', expect.any(Object), expect.any(String))
  expect(model.engine.sync).toHaveBeenCalledWith(true)
  expect(wrapper.text()).toContain('Two-way sync is ready')
})

it('a scanned QR never overwrites an already paired vault', async () => {
  const wrapper = mount(PhoneApp, { props: { takeHandoff: () => ({ recovery: fixture.crypto.recovery, email: 'synthetic@example.invalid' }) } }); await flushPromises()
  expect(wrapper.text()).toContain('Unlock offline')
  expect(wrapper.text()).not.toContain('Connect this phone')
  expect(model.engine.pair).not.toHaveBeenCalled()
})

it('reconnects and catches up an unlocked vault with one button while offline unlock stays independent', async () => {
  model.unlocked = true
  const wrapper = mount(PhoneApp); await flushPromises()
  await button(wrapper, 'Connect and sync').trigger('click'); await flushPromises()
  expect(model.auth.connect).toHaveBeenCalledWith({ prompt: '', loginHint: 'synthetic@example.invalid' })
  expect(model.engine.sync).toHaveBeenCalledWith(true)
  expect(wrapper.text()).toContain('Two-way sync is ready')
})
