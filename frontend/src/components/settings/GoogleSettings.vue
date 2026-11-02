<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { nextTick, onMounted, ref, useId } from 'vue'
import Button from 'primevue/button'
import { testGoogleDrive, type GoogleCapability, type GoogleConnection } from '../../api'
import { googleLogin } from '../../googleAuth'
import SyncSettings from '../sync/SyncSettings.vue'
import ProviderButtons from '../auth/ProviderButtons.vue'
import GoogleSetup from './GoogleSetup.vue'
defineProps<{ googleOnly?: boolean; onboarding?: boolean }>()
const id = useId()

const connection = ref<GoogleConnection | null>(null)
const choices = ref<GoogleCapability[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const recoveryKey = ref('')
const setupOpen = ref(false)
const providerButtons = ref<InstanceType<typeof ProviderButtons> | null>(null)
const labels: { key: GoogleCapability; label: string }[] = [
  { key: 'drive', get label() { return t("Drive app data (optional)") } },
  { key: 'gmail_read', get label() { return t("Read and search Gmail") } },
  { key: 'gmail_drafts', get label() { return t("Create Gmail drafts") } },
]
async function load() {
  try {
    connection.value = await googleLogin.status()
    choices.value = labels.filter(item => connection.value?.capabilities[item.key]).map(item => item.key)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to load Google connection.") }
}
async function perform(action: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Google connection failed.") }
  finally { busy.value = false }
}
async function connect() {
  if (busy.value) return
  if (!connection.value) await load()
  if (!connection.value) return
  if (!connection.value.configured) {
    setupOpen.value = true; error.value = ''
    await nextTick()
    document.getElementById('google-setup-title')?.focus()
    return
  }
  return perform(async () => {
  window.location.assign(await googleLogin.authorizationUrl(choices.value))
  })
}
async function configured() {
  setupOpen.value = false
  const selected = [...choices.value]
  await load()
  choices.value = selected
  notice.value = t("Google registration saved. Connect your account; Gmail and Drive access are optional.")
}
function connectAgent(provider: 'chatgpt' | 'claude') {
  window.location.hash = `#/settings?tab=agent&provider=${provider}`
}
async function disconnect() {
  await perform(async () => {
    connection.value = await googleLogin.disconnect(); choices.value = []
    notice.value = t("Google logged out of this tracker. Local records and agent access are available.")
  })
  await nextTick()
  if (!connection.value?.email) providerButtons.value?.focusGoogle()
}
function driveTest() { return perform(async () => {
  try { notice.value = (await testGoogleDrive(recoveryKey.value.trim())).message }
  finally { recoveryKey.value = '' }
}) }
onMounted(load)
</script>

<template>
  <section class="google-panel" :aria-labelledby="`${id}-google-title`">
    <h3 :id="`${id}-google-title`">{{ googleOnly ? t("Google account · optional") : t("Connect your accounts") }}</h3>
    <p>{{ googleOnly ? t("Link Google, then choose whether to allow Gmail and Drive access.") : t("Choose Google for Gmail and Drive, or connect ChatGPT and Claude to your tracker.") }}</p>
    <ProviderButtons ref="providerButtons" :disabled="busy" :google-only="googleOnly" :google-user="connection?.email" :google-status="connection?.status" @google="connect" @google-logout="disconnect" @chatgpt="connectAgent('chatgpt')" @claude="connectAgent('claude')" />
    <GoogleSetup v-if="setupOpen" @saved="configured" @close="setupOpen = false" />
    <p v-if="!connection && !error" role="status">{{ t("Loading Google connection…") }}</p>
    <template v-if="connection">
      <p v-if="!connection.email">{{ t("No account connected") }}</p>
      <p v-if="connection.message" role="alert">{{ messageText(String((connection.message) ?? '')) }}</p>
      <fieldset :disabled="busy">
        <legend>{{ t("Google capabilities") }}</legend>
        <label v-for="item in labels" :key="item.key"><input v-model="choices" type="checkbox" :value="item.key" /> {{ messageText(String((item.label) ?? '')) }} <small>{{ connection.capabilities[item.key] ? t("Granted") : t("Not granted") }}</small></label>
      </fieldset>
      <p>{{ t("Changing capabilities opens a new Google consent flow. Reconnect with the same account; disconnect first to choose another. Gmail drafts are created only on request. Nothing is sent.") }}</p>
      <p v-if="connection.configured && !connection.email && !choices.length">{{ t("Connect your Google account now. Gmail and Drive permissions are optional.") }}</p>
      <div class="actions"><Button v-if="connection.email" type="button" severity="secondary" :disabled="busy" @click="connect">{{ t("Reconnect Google") }}</Button><Button type="button" severity="secondary" :disabled="busy" @click="load">{{ t("Refresh connection") }}</Button></div>
      <details v-if="connection.capabilities.drive"><summary>{{ t("Test encrypted Drive app data") }}</summary><p>{{ t("Use a 32-byte base64 recovery key you generated and saved yourself. Keep it separate from your tracker and Google credentials. This verifies and removes one encrypted test object. Phone sync is not enabled.") }}</p><label :for="`${id}-drive-key`">{{ t("Your recovery key") }}</label><input :id="`${id}-drive-key`" v-model="recoveryKey" type="password" autocomplete="off" spellcheck="false" /><Button type="button" :disabled="busy || !recoveryKey.trim()" @click="driveTest">{{ t("Test encrypted app data") }}</Button></details>
    </template>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p><p v-if="notice" class="at-message success" role="status">{{ messageText(String((notice) ?? '')) }}</p>
    <details v-if="!onboarding"><summary>{{ t("Set up or manage device sync") }}</summary><SyncSettings :drive-ready="Boolean(connection?.capabilities.drive)" :account-email="connection?.email" /></details>
  </section>
</template>

<style scoped>
.google-panel{background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;padding:24px;margin:20px 0}.google-panel p{color:var(--at-text-muted);line-height:1.5}fieldset{display:grid;gap:12px;border:1px solid var(--at-border);padding:16px}label{display:block}small{color:var(--at-text-muted);margin-left:8px}.actions{display:flex;flex-wrap:wrap;gap:10px}details{margin-block:18px}summary{cursor:pointer;font-weight:600}input[type=password]{display:block;max-width:100%;width:32em;margin:8px 0;padding:8px}
</style>
