<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import QRCode from 'qrcode'
import { syncClient, type SyncStatus } from '../../syncClient'
import { pairingUrl, publicPhoneUrl } from '../../phone/core/pairing'
const props = defineProps<{ driveReady: boolean; accountEmail?: string | null }>()
const emit = defineEmits<{ prepared: [status: SyncStatus] }>()
const phoneUrl = publicPhoneUrl(import.meta.env.VITE_PHONE_URL ?? '')
const qr = ref(''), backup = ref(''), busy = ref(false), error = ref('')
let timer: ReturnType<typeof setTimeout> | undefined, generation = 0
function hide() { generation++; clearTimeout(timer); qr.value = ''; backup.value = '' }
async function prepare() {
  if (busy.value || !props.driveReady) return
  hide(); busy.value = true; error.value = ''; const attempt = generation
  try {
    if (!props.accountEmail) throw new Error('Refresh the Google connection before pairing.')
    const result = await syncClient.preparePhone()
    const image = await QRCode.toDataURL(pairingUrl(phoneUrl, { recovery: result.recovery_export, email: props.accountEmail }), { width: 280, margin: 2, errorCorrectionLevel: 'M' })
    if (attempt !== generation) return
    emit('prepared', result.status); qr.value = image; backup.value = result.recovery_export
    // Treat this image like a recovery key. Never persist, log or upload it.
    timer = setTimeout(hide, 5 * 60_000)
  } catch (reason) { if (attempt === generation) error.value = reason instanceof Error ? reason.message : 'Phone setup could not complete. Try again.' }
  finally { busy.value = false }
}
onMounted(() => window.addEventListener('pagehide', hide))
onBeforeUnmount(() => { hide(); window.removeEventListener('pagehide', hide) })
</script>
<template>
  <section v-if="phoneUrl" class="phone-pairing" aria-label="Pair Android phone">
    <h4>Connect your phone</h4>
    <p>Pairing enables compact encrypted sync through your Google account. Phone and desktop edits synchronize both ways.</p>
    <button type="button" :disabled="busy || !driveReady" @click="prepare">{{ busy ? 'Preparing phone sync…' : 'Pair phone' }}</button>
    <p v-if="!driveReady">Connect Google with Drive app data permission first.</p>
    <div v-if="qr" role="status">
      <p>Scan this private QR with your Android camera. On the phone, choose an offline passphrase and tap Connect and sync. Google may ask you to approve sign-in.</p>
      <img :src="qr" width="280" height="280" alt="Private phone pairing QR — keep it secret" />
      <p>This QR contains your recovery key. Only scan it on your phone; do not share or photograph it. It hides here after five minutes.</p>
      <p>If the private site asks for ChatGPT sign-in, finish signing in and scan this QR again.</p>
      <button type="button" @click="hide">Hide pairing QR</button>
      <details><summary>Save a separate recovery backup</summary><p>Keep this export somewhere safe, separate from Google.</p><textarea :value="backup" readonly rows="3" autocomplete="off" spellcheck="false" aria-label="Recovery backup export" /></details>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <details><summary>Open without a pairing QR</summary><a :href="phoneUrl" target="_blank" rel="noopener noreferrer">Open the phone app</a><p>Use the recovery export under advanced setup if you cannot scan.</p></details>
  </section>
</template>
<style scoped>.phone-pairing{margin:18px 0;padding:16px;border:1px solid var(--at-border,#b5bdb3);border-radius:8px}.phone-pairing img{display:block;max-width:100%;height:auto;background:white}.phone-pairing button{min-height:44px;padding:10px 16px;margin:8px 0;background:var(--at-primary,#1c5b53);color:white;border:0;border-radius:6px;font:inherit;cursor:pointer}.phone-pairing button:disabled{opacity:.6;cursor:default}.phone-pairing a{display:inline-block;min-height:44px;padding:10px 0;overflow-wrap:anywhere}.phone-pairing p{line-height:1.5}</style>
