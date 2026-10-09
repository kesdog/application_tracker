// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import PhoneNotifications from './components/settings/PhoneNotifications.vue'
const api = vi.hoisted(() => ({ getPhoneNotificationStatus:vi.fn(), registerPhoneDevice:vi.fn(), removePhoneDevice:vi.fn(), testPhoneDevice:vi.fn() }))
vi.mock('./api', () => api)
enableAutoUnmount(afterEach)
const key = btoa(String.fromCharCode(...Array(65).fill(4)))
const device = {id:'device-1',label:'My phone',active:true,reason:null,created_at:'2026-10-09',latest:null}
let requestPermission: ReturnType<typeof vi.fn>
let subscribe: ReturnType<typeof vi.fn>
let unsubscribe: ReturnType<typeof vi.fn>
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear()
  api.getPhoneNotificationStatus.mockResolvedValue({configured:true,public_key:key,devices:[]})
  api.registerPhoneDevice.mockResolvedValue(device)
  api.testPhoneDevice.mockResolvedValue({message:'Test queued; acceptance is not display confirmation.'})
  requestPermission = vi.fn().mockResolvedValue('granted')
  unsubscribe = vi.fn().mockResolvedValue(true)
  subscribe = vi.fn().mockResolvedValue({toJSON:()=>({endpoint:'https://fcm.googleapis.com/a',keys:{auth:'key',p256dh:'public'}}),unsubscribe})
  vi.stubGlobal('isSecureContext',true)
  vi.stubGlobal('PushManager',class {})
  vi.stubGlobal('Notification',{permission:'default',requestPermission})
  vi.stubGlobal('navigator',{serviceWorker:{getRegistration:vi.fn().mockResolvedValue({active:{},pushManager:{subscribe,getSubscription:vi.fn().mockResolvedValue(null)}})}})
})
afterEach(() => vi.unstubAllGlobals())

it('checks status without asking permission or subscribing on mount',async()=>{
  const wrapper=mount(PhoneNotifications); await flushPromises()
  expect(wrapper.text()).toContain('Browser permission: default')
  expect(requestPermission).not.toHaveBeenCalled(); expect(subscribe).not.toHaveBeenCalled()
})
it('asks permission only on enable and registers with the VAPID key',async()=>{
  const wrapper=mount(PhoneNotifications); await flushPromises()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(requestPermission).toHaveBeenCalledOnce()
  expect(subscribe).toHaveBeenCalledWith(expect.objectContaining({userVisibleOnly:true,applicationServerKey:expect.any(Uint8Array)}))
  expect(api.registerPhoneDevice).toHaveBeenCalledWith(expect.objectContaining({endpoint:'https://fcm.googleapis.com/a'}),'My phone')
  expect(localStorage.getItem('tracker-phone-device')).toBe('device-1')
})
it('keeps manual use available after permission denial',async()=>{
  requestPermission.mockResolvedValue('denied')
  const wrapper=mount(PhoneNotifications); await flushPromises()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('keep using the follow-up queue')
  expect(subscribe).not.toHaveBeenCalled(); expect(api.registerPhoneDevice).not.toHaveBeenCalled()
})
it('shows a browser permission error without an unhandled opt-in failure',async()=>{
  requestPermission.mockImplementation(()=>{throw new Error('Browser denied this request')})
  const wrapper=mount(PhoneNotifications);await flushPromises()
  await wrapper.get('button').trigger('click');await flushPromises()
  expect(wrapper.text()).toContain('Browser denied this request')
  expect(subscribe).not.toHaveBeenCalled()
})
it('does not offer enable when the server or browser cannot deliver',async()=>{
  api.getPhoneNotificationStatus.mockResolvedValue({configured:false,public_key:null,devices:[]})
  const wrapper=mount(PhoneNotifications); await flushPromises()
  expect(wrapper.text()).toContain('server push-key setup')
  expect(wrapper.findAll('button').map(item=>item.text())).not.toContain('Enable notifications')
})
it('replaces a subscription the server marked expired before enabling again',async()=>{
  localStorage.setItem('tracker-phone-device','device-1')
  api.getPhoneNotificationStatus.mockResolvedValue({configured:true,public_key:key,devices:[{...device,active:false,reason:'Expired subscription'}]})
  const staleUnsubscribe=vi.fn().mockResolvedValue(true)
  const getSubscription=vi.fn().mockResolvedValue({options:{applicationServerKey:Uint8Array.from(Array(65).fill(4)).buffer},unsubscribe:staleUnsubscribe})
  vi.stubGlobal('navigator',{serviceWorker:{getRegistration:vi.fn().mockResolvedValue({active:{},pushManager:{getSubscription,subscribe}})}})
  const wrapper=mount(PhoneNotifications);await flushPromises()
  await wrapper.get('button').trigger('click');await flushPromises()
  expect(staleUnsubscribe).toHaveBeenCalledOnce();expect(subscribe).toHaveBeenCalledOnce()
  expect(api.registerPhoneDevice).toHaveBeenCalledOnce()
})
it('removes the server registration and unsubscribes only this device',async()=>{
  localStorage.setItem('tracker-phone-device','device-1')
  api.getPhoneNotificationStatus.mockResolvedValue({configured:true,public_key:key,devices:[device]})
  const getSubscription=vi.fn().mockResolvedValue({unsubscribe})
  vi.stubGlobal('navigator',{serviceWorker:{getRegistration:vi.fn().mockResolvedValue({pushManager:{getSubscription}})}})
  const wrapper=mount(PhoneNotifications); await flushPromises()
  await wrapper.findAll('button').find(item=>item.text()==='Remove My phone')!.trigger('click'); await flushPromises()
  expect(api.removePhoneDevice).toHaveBeenCalledWith('device-1'); expect(unsubscribe).toHaveBeenCalledOnce()
  expect(localStorage.getItem('tracker-phone-device')).toBeNull()
})
