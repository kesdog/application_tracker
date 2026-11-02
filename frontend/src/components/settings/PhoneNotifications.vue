<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { computed, onMounted, ref } from 'vue'
import { getPhoneNotificationStatus, registerPhoneDevice, removePhoneDevice, testPhoneDevice, type PhoneNotificationStatus } from '../../api'
const status = ref<PhoneNotificationStatus | null>(null)
const busy = ref(false)
const error = ref('')
const message = ref('')
const label = ref('My phone')
const supported = window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
const permission = ref(supported ? Notification.permission : 'unavailable')
let savedId = ''
try { savedId = localStorage.getItem('tracker-phone-device') ?? '' } catch { /* Registration can work without local storage. */ }
const currentId = ref(savedId)
const current = computed(() => status.value?.devices.find(item => item.id === currentId.value))
function remember(id: string) {
  currentId.value = id
  try { if (id) localStorage.setItem('tracker-phone-device', id); else localStorage.removeItem('tracker-phone-device') } catch { /* In-memory ID still supports this visit. */ }
}
async function refresh() {
  try { status.value = await getPhoneNotificationStatus(); if (supported) permission.value = Notification.permission }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to check phone notifications.") }
}
function bytes(value: string) {
  return Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4)), character => character.charCodeAt(0))
}
async function enable() {
  if (!supported || !status.value?.public_key) return
  // This call must begin directly in the click handler, including on iPhone.
  busy.value = true; error.value = ''; message.value = ''
  try {
    const choice = Notification.permission === 'granted' ? Promise.resolve('granted') : Notification.requestPermission()
    permission.value = await choice
    if (permission.value !== 'granted') { message.value = t("Notifications were not enabled. You can keep using the follow-up queue."); return }
    const registration = await navigator.serviceWorker.getRegistration('/')
    if (!registration?.active) throw new Error(t("Reload the tracker to finish phone setup, then try again."))
    const key = bytes(status.value.public_key)
    let subscription = await registration.pushManager.getSubscription()
    const previousKey = subscription?.options.applicationServerKey
    if (subscription && ((current.value && !current.value.active) || (previousKey && Array.from(new Uint8Array(previousKey)).join(',') !== Array.from(key).join(',')))) { await subscription.unsubscribe(); subscription = null }
    subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
    const device = await registerPhoneDevice(subscription.toJSON(), label.value)
    remember(device.id)
    message.value = t("Phone reminders enabled. Use Test notification to check background delivery.")
    await refresh()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to enable this device.") }
  finally { busy.value = false }
}
async function remove(id: string) {
  busy.value = true; error.value = ''; message.value = ''
  try {
    await removePhoneDevice(id)
    if (id === currentId.value) {
      remember('')
      const registration = supported ? await navigator.serviceWorker.getRegistration('/') : null
      await (await registration?.pushManager.getSubscription())?.unsubscribe()
    }
    message.value = t("Device removed from phone reminders. Browser notification permission is managed in browser settings.")
    await refresh()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to finish removing this device. Check its status and try again."); await refresh() }
  finally { busy.value = false }
}
async function test() {
  busy.value = true; error.value = ''; message.value = ''
  try { message.value = (await testPhoneDevice(currentId.value)).message; await refresh() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to queue a test.") }
  finally { busy.value = false }
}
onMounted(refresh)
</script>

<template>
  <section class="phone-panel" aria-labelledby="phone-notifications-heading">
    <h3 id="phone-notifications-heading">{{ t("Phone notifications") }}</h3>
    <p v-if="!status && !error" role="status">{{ t("Checking notification setup…") }}</p>
    <p v-if="status && !status.configured">{{ t("Phone notifications need an HTTPS hosted workspace and server push-key setup. Your in-app reminders remain available.") }}</p>
    <p v-if="!supported">{{ t("This browser cannot receive Web Push here. On iPhone, open the app from its Home Screen icon; use a supported browser on Android.") }}</p>
    <template v-if="supported && status?.configured">
      <p>{{ t("Browser permission:") }} {{ messageText(permission) }}{{ t(". This device:") }} {{ current?.active ? t('Enabled') : t("not registered") }}.</p>
      <p v-if="permission === 'denied'">{{ t("Notifications are blocked. Change the permission in browser or phone settings, then check again.") }}</p>
      <label>{{ t("Device name") }}<input v-model="label" maxlength="80" :disabled="busy" /></label>
      <div class="actions"><button type="button" :disabled="busy || permission === 'denied' || !label.trim()" @click="enable">{{ current?.active ? t("Update this device") : t("Enable notifications") }}</button><button type="button" :disabled="busy || !current?.active" @click="test">{{ t("Test notification") }}</button></div>
      <p>{{ t("Permission is requested only when you enable this device. Notifications show a generic reminder; details open after sign-in. Signing out does not remove an opted-in device.") }}</p>
    </template>
    <p v-if="status?.configured">{{ t("Reminder timing, quiet hours and daily digest are in Settings → Follow-ups → Schedule & reminder rules. Tests bypass quiet hours.") }}</p>
    <ul v-if="status?.devices.length"><li v-for="device in status.devices" :key="device.id"><strong>{{ device.label }}</strong> · {{ device.active ? t("Enabled") : t("Inactive") }}<span v-if="device.id === currentId"> {{ t("· This device") }}</span><p v-if="device.reason">{{ messageText(String((device.reason) ?? '')) }}</p><p v-if="device.latest">{{ t("Latest delivery:") }} {{ messageText(String((device.latest.state.toLowerCase()) ?? '')) }}<span v-if="device.latest.error"> — {{ errorText(String((device.latest.error) ?? '')) }}</span>{{ t(". Accepted means the push service accepted it; it does not prove the phone displayed it.") }}</p><button type="button" :disabled="busy" @click="remove(device.id)">{{ t("Remove") }} {{ device.label }}</button></li></ul>
    <button type="button" :disabled="busy" @click="refresh">{{ t("Check notification status") }}</button>
    <p v-if="message" role="status">{{ messageText(String((message) ?? '')) }}</p><p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
  </section>
</template>

<style scoped>
.phone-panel{margin:20px 0;padding:24px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}p,li{line-height:1.6;overflow-wrap:anywhere}ul{padding-left:20px}li{margin:16px 0}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}label{display:block}input{display:block;box-sizing:border-box;width:min(100%,340px);padding:10px;margin-top:8px;border:1px solid var(--at-border);border-radius:6px}button{font:inherit;padding:10px 14px;background:var(--at-surface-muted);border:1px solid var(--at-border);border-radius:6px;color:var(--at-text);cursor:pointer}button:disabled{opacity:.6;cursor:not-allowed}@media(max-width:650px){.phone-panel{padding:16px}}
</style>
