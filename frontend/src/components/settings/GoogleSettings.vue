<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import { testGoogleDrive, type GoogleCapability, type GoogleConnection } from '../../api'
import { googleLogin } from '../../googleAuth'
import SyncSettings from '../sync/SyncSettings.vue'

const connection = ref<GoogleConnection | null>(null)
const choices = ref<GoogleCapability[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const recoveryKey = ref('')
const labels: { key: GoogleCapability; label: string }[] = [
  { key: 'drive', label: 'Drive app data (optional)' },
  { key: 'gmail_read', label: 'Read and search Gmail' },
  { key: 'gmail_drafts', label: 'Create Gmail drafts' },
]
async function load() {
  try {
    connection.value = await googleLogin.status()
    choices.value = labels.filter(item => connection.value?.capabilities[item.key]).map(item => item.key)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load Google connection.' }
}
async function perform(action: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Google connection failed.' }
  finally { busy.value = false }
}
function connect() { return perform(async () => {
  window.location.assign(await googleLogin.authorizationUrl(choices.value))
}) }
function disconnect() { return perform(async () => {
  connection.value = await googleLogin.disconnect(); choices.value = []
  notice.value = 'Google disconnected from this tracker. Local records and agent access are available.'
}) }
function driveTest() { return perform(async () => {
  try { notice.value = (await testGoogleDrive(recoveryKey.value.trim())).message }
  finally { recoveryKey.value = '' }
}) }
onMounted(load)
</script>

<template>
  <section class="google-panel" aria-labelledby="google-account-title">
    <h3 id="google-account-title">Google account</h3>
    <p>Connect one account for ChatGPT and Claude to use through this tracker's shared permissions. Local tracking works without Google.</p>
    <p v-if="!connection && !error" role="status">Loading Google connection…</p>
    <template v-if="connection">
      <p><strong>{{ connection.email || 'No account connected' }}</strong> · {{ connection.status.replaceAll('_', ' ').toLowerCase() }}</p>
      <p v-if="connection.message" role="alert">{{ connection.message }}</p>
      <p v-if="!connection.configured">To enable connection, configure GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI on the tracker backend. See the Google integration setup guide in the repository.</p>
      <fieldset :disabled="busy || !connection.configured">
        <legend>Google capabilities</legend>
        <label v-for="item in labels" :key="item.key"><input v-model="choices" type="checkbox" :value="item.key" /> {{ item.label }} <small>{{ connection.capabilities[item.key] ? 'Granted' : 'Not granted' }}</small></label>
      </fieldset>
      <p>Changing capabilities opens a new Google consent flow. Reconnect with the same account; disconnect first to choose another. Gmail drafts are created only on request. Nothing is sent.</p>
      <div class="actions"><Button type="button" :disabled="busy || !connection.configured || !choices.length" @click="connect">{{ connection.email ? 'Reconnect Google' : 'Connect Google' }}</Button><Button v-if="connection.email || connection.status !== 'DISCONNECTED'" type="button" severity="secondary" :disabled="busy" @click="disconnect">Disconnect Google</Button><Button type="button" severity="secondary" :disabled="busy" @click="load">Refresh connection</Button></div>
      <details v-if="connection.capabilities.drive"><summary>Test encrypted Drive app data</summary><p>Use a 32-byte base64 recovery key you generated and saved yourself. Keep it separate from your tracker and Google credentials. This verifies and removes one encrypted test object. Phone sync is not enabled.</p><label for="drive-recovery-key">Your recovery key</label><input id="drive-recovery-key" v-model="recoveryKey" type="password" autocomplete="off" spellcheck="false" /><Button type="button" :disabled="busy || !recoveryKey.trim()" @click="driveTest">Test encrypted app data</Button></details>
    </template>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <SyncSettings :drive-ready="Boolean(connection?.capabilities.drive)" />
  </section>
</template>

<style scoped>
.google-panel{background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;padding:24px;margin:20px 0}.google-panel p{color:var(--at-text-muted);line-height:1.5}fieldset{display:grid;gap:12px;border:1px solid var(--at-border);padding:16px}label{display:block}small{color:var(--at-text-muted);margin-left:8px}.actions{display:flex;flex-wrap:wrap;gap:10px}details{margin-top:18px}input[type=password]{display:block;max-width:100%;width:32em;margin:8px 0;padding:8px}
</style>
