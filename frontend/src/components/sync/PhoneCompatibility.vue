<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { GoogleAuthorization, loadGoogleOAuth } from '../../phone/core/auth'
import { GoogleDriveTransport } from '../../phone/core/drive'
import { verifyCrossClient } from '../../phone/core/compatibility'
import { syncClient } from '../../syncClient'
const props = defineProps<{ accountEmail?: string | null }>()
const clientId = ref(import.meta.env.VITE_PHONE_GOOGLE_CLIENT_ID || '')
const busy = ref(false), ready = ref(false), preparing = ref(false), stage = ref(''), notice = ref(''), error = ref('')
let attempt = 0, active: GoogleAuthorization | undefined
async function prepare() {
  if (ready.value || preparing.value) return
  preparing.value = true; error.value = ''
  try { await loadGoogleOAuth(); ready.value = true }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Google sign-in could not load.' }
  finally { preparing.value = false }
}
function opened(event: Event) {
  // Load the optional Google SDK only after the person opens this section.
  if ((event.target as HTMLDetailsElement).open) void prepare()
}
function cancel() {
  attempt++; active?.clear(); active = undefined; busy.value = false; stage.value = ''
  error.value = 'Google sign-in cancelled. Close the Google popup, then retry.'
}
async function verify(resumeExisting = false) {
  const current = ++attempt
  busy.value = true; stage.value = 'Waiting for Google sign-in. Choose the desktop account in the popup.'; notice.value = ''; error.value = ''
  const auth = new GoogleAuthorization(clientId.value.trim()); active = auth
  try {
    await auth.connect(resumeExisting ? { prompt: '', ...(props.accountEmail ? { loginHint: props.accountEmail } : {}) } : undefined)
    // A cancelled or older popup must never start a probe or replace a newer result.
    if (current !== attempt) return
    stage.value = 'Checking encrypted file visibility and change feeds through both Google clients…'
    await verifyCrossClient(clientId.value.trim(), auth, new GoogleDriveTransport(auth), syncClient)
    if (current === attempt) notice.value = 'Verified live: both OAuth clients discovered, decrypted and observed each other’s encrypted probe through the change feed. Disposable probe files were cleaned up.'
  } catch (reason) { if (current === attempt) error.value = reason instanceof Error ? reason.message : 'Live compatibility check failed.' }
  finally { auth.clear(); if (current === attempt) { active = undefined; busy.value = false; stage.value = '' } }
}
onBeforeUnmount(() => { attempt++; active?.clear(); active = undefined })
</script>
<template>
  <details class="phone-check" @toggle="opened"><summary>Verify the phone Google client</summary>
    <p>Use a separate Web OAuth client in the desktop client’s Google Cloud project. Add this page’s origin to its allowed JavaScript origins, then authorize the same Google account. Both clients need Drive app-data permission.</p>
    <form @submit.prevent="verify()"><label>Phone Web OAuth public client ID <input v-model="clientId" :disabled="busy" required autocomplete="off" spellcheck="false" /></label><button :disabled="busy || !ready || !clientId.trim()">{{ preparing ? 'Preparing Google sign-in…' : busy ? 'Checking live Google access…' : 'Connect phone client and verify both directions' }}</button><button v-if="busy && stage.startsWith('Waiting')" type="button" @click="cancel">Cancel sign-in</button></form>
    <p v-if="busy" role="status">{{ stage }}</p>
    <button v-if="!ready && error" type="button" :disabled="preparing" @click="prepare">Retry Google setup</button>
    <p>Only empty encrypted test batches are exchanged. Workspace data, recovery exports and desktop tokens are not transferred.</p>
    <p v-if="notice" role="status">{{ notice }}</p><p v-if="error" role="alert">{{ error }}</p>
    <button v-if="ready && !busy && clientId.trim()" type="button" @click="verify(true)">Use existing Google sign-in</button>
    <a href="/phone/" target="_blank" rel="noopener">Open the independent phone app</a>
  </details>
</template>
<style scoped>.phone-check{margin:16px 0}p{line-height:1.6}label{display:block}input{display:block;box-sizing:border-box;width:100%;max-width:38em;padding:10px;margin:8px 0}button{padding:10px;min-height:44px;margin-right:8px}</style>
