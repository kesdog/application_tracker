<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { onMounted, ref } from 'vue'
import { getGoogleClientSetup, saveGoogleClientSetup, type GoogleClientSetup } from '../../api'

const emit = defineEmits<{ saved: []; close: [] }>()
const setup = ref<GoogleClientSetup | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const subjects = ref('')
async function load() {
  error.value = ''
  try { setup.value = await getGoogleClientSetup() }
  catch { error.value = t("Unable to load Google setup. Try again.") }
}
async function copy(value: string) {
  try { await navigator.clipboard.writeText(value); notice.value = t("Copied.") }
  catch { notice.value = t("Copy the address shown below.") }
}
async function importRegistration(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (file.size > 65536) throw new Error(t("Choose the small JSON credentials file downloaded from Google Cloud."))
    let document: { web?: { client_id?: unknown; client_secret?: unknown }; installed?: { client_id?: unknown; client_secret?: unknown } }
    try { document = JSON.parse(await file.text()) } catch { throw new Error(t("This is not a Google credentials JSON file. Download it from your Google Cloud OAuth client.")) }
    const client = document?.web || document?.installed
    if (!client || typeof client.client_id !== 'string' || !/^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(client.client_id)) throw new Error(t("Choose the OAuth client JSON downloaded from Google Cloud, rather than a service-account file."))
    if (setup.value?.hosted && !document.web) throw new Error(t("This hosted workspace needs a Web application client. Download its JSON from Google Cloud."))
    if (client.client_secret !== undefined && typeof client.client_secret !== 'string') throw new Error(t("The Google credentials file is invalid. Download it again."))
    await saveGoogleClientSetup({ client_id: client.client_id, ...(client.client_secret ? { client_secret: client.client_secret } : {}), ...(subjects.value.trim() ? { login_subjects: subjects.value.trim() } : {}) })
    emit('saved')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to save Google setup. Try again.") }
  finally { input.value = ''; busy.value = false }
}
onMounted(load)
</script>

<template>
  <section class="google-setup" aria-labelledby="google-setup-title">
    <h4 id="google-setup-title" tabindex="-1">{{ t("Connect Google to this installation") }}</h4>
    <p>{{ t("Google requires a one-time app registration before it can show the account chooser. Once registered, import its credentials here and connect. No backend edits or restart.") }}</p>
    <p v-if="!setup && !error" role="status">{{ t("Loading connection addresses…") }}</p>
    <template v-if="setup">
      <ol>
        <li>{{ t("In Google Cloud, create or select a project named") }} <strong>{{ t("Application Tracker") }}</strong>{{ t(". Complete Google Auth Platform branding and audience; add your account as a test user while the app is in testing.") }}</li>
        <li>{{ t("Create an OAuth client of type") }} <strong>{{ setup.hosted ? t("Web application") : t("Desktop app") }}</strong>. {{ setup.hosted ? t("Register these exact addresses:") : t("Google uses a local callback for desktop apps; you do not need to register these addresses in Google Cloud.") }}
          <div class="address"><span>{{ setup.hosted ? t("Authorized JavaScript origin") : t("This installation") }}</span><code>{{ setup.origin }}</code><button type="button" @click="copy(setup.origin)">{{ t("Copy origin") }}</button></div>
          <div class="address"><span>{{ setup.hosted ? t("Authorized redirect URI") : t("Local callback") }}</span><code>{{ setup.redirect_uri }}</code><button type="button" @click="copy(setup.redirect_uri)">{{ t("Copy callback") }}</button></div>
        </li>
        <li>{{ t("Enable Gmail API for mail access and Google Drive API for sync, if you plan to use them. Download the OAuth client's JSON credentials, then import that file below.") }}</li>
      </ol>
      <a href="https://console.cloud.google.com/auth/clients" target="_blank" rel="noopener noreferrer">{{ t("Open Google Cloud") }}</a>
      <label class="import-label" for="google-client-file">{{ busy ? t("Saving Google connection…") : t("Import Google credentials JSON") }}</label>
      <input id="google-client-file" type="file" accept=".json,application/json" :disabled="busy" @change="importRegistration" />
      <details v-if="setup.hosted"><summary>{{ t("Also allow Google workspace sign-in") }}</summary><p>{{ t("Optional: enter the trusted Google account subject IDs allowed to open this shared workspace. Password sign-in remains available.") }}</p><label for="google-allowed-subjects">{{ t("Allowed account IDs, separated by commas") }}</label><input id="google-allowed-subjects" v-model="subjects" type="text" autocomplete="off" :disabled="busy" /></details>
      <p class="hint">{{ t("Credentials are saved in this installation's secure credential store and are not sent to ChatGPT or Claude.") }}</p>
    </template>
    <p v-if="error" role="alert">{{ errorText(String((error) ?? '')) }}</p><p v-if="notice" role="status">{{ messageText(String((notice) ?? '')) }}</p>
    <button v-if="!setup && error" type="button" @click="load">{{ t("Try again") }}</button>
    <button type="button" :disabled="busy" @click="emit('close')">{{ t("Close setup") }}</button>
  </section>
</template>

<style scoped>
.google-setup{border:1px solid var(--at-border);border-radius:8px;padding:20px;margin-top:20px;overflow-wrap:anywhere}.google-setup p,.google-setup li{line-height:1.6;color:var(--at-text-muted)}li+li{margin-top:12px}ol{padding-left:24px}.address{display:grid;gap:6px;margin:12px 0;padding:12px;background:var(--at-surface-muted);border-radius:6px}.address code{color:var(--at-text);word-break:break-all}.google-setup button,.google-setup a{box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 14px;border:1px solid var(--at-border);border-radius:6px;font:inherit;color:var(--at-text);background:var(--at-surface);cursor:pointer;text-decoration:none}.google-setup :is(button,a,input,summary):focus-visible{outline:3px solid var(--at-focus);outline-offset:3px}.import-label{display:block;font-weight:600;margin:20px 0 8px}input{box-sizing:border-box;max-width:100%;min-height:44px}details{margin:20px 0}.hint{font-size:13px}[role=alert]{color:var(--at-unsuccessful)}
</style>
