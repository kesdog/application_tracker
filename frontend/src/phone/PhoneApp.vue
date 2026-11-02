<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createRuntime } from './runtime'
import { IndexedReplicaStore, type RecordState } from './core/storage'
import type { Entity, State } from './core/protocol'
import type { PairingHandoff } from './core/pairing'
const props = defineProps<{ takeHandoff?: () => PairingHandoff | undefined; pairingError?: string }>()
let incoming = props.takeHandoff?.()
const scanned = ref(Boolean(incoming)), accountHint = ref(incoming?.email ?? '')
const store = new IndexedReplicaStore()
const clientId = ref(import.meta.env.VITE_PHONE_GOOGLE_CLIENT_ID ?? '')
let runtime = createRuntime(store, clientId.value), configuredClient = clientId.value
const paired = ref(false), unlocked = ref(false), connected = ref(false), email = ref(''), busy = ref(false), syncing = ref(false), ready = ref(false)
const supported = ref(true)
const recovery = ref(incoming?.recovery ?? ''), passphrase = ref(''), confirmation = ref(''), error = ref(props.pairingError ?? ''), notice = ref(''), records = ref<RecordState[]>([])
incoming = undefined
const pending = ref<number | null>(null), conflicts = ref<number | null>(null), lastSuccess = ref<string | null>(null)
const selected = ref<RecordState | null>(null), entity = ref<Entity>('application'), draft = ref<State>({}), editing = ref(false), reviewed = ref(false)
const resolutions = ref<Record<string, State>>({}), confirmed = ref<Record<string, boolean>>({})
const applications = computed(() => records.value.filter(row => row.entity === 'application' && !row.state.deleted && Object.keys(row.state).length))
const visible = computed(() => records.value.filter(row => !row.state.deleted && Object.keys(row.state).length))
const reviews = computed(() => records.value.filter(row => row.reason && row.heads.length && row.variants.length && !['missing_application', 'missing_ancestors'].includes(row.reason)))
let debounce: ReturnType<typeof setTimeout> | undefined, inactivity: ReturnType<typeof setTimeout> | undefined, poll: ReturnType<typeof setInterval> | undefined
let lastActivity = Date.now()
function message(reason: unknown) { return reason instanceof Error ? reason.message : 'The operation could not complete. Local data was preserved.' }
async function refresh() {
  const status = await runtime.engine.status()
  paired.value = status.paired; unlocked.value = status.unlocked; pending.value = status.pending; conflicts.value = status.conflicts; lastSuccess.value = status.lastSuccess
  error.value = status.error ?? ''; syncing.value = runtime.engine.syncing
  if (status.unlocked) records.value = await runtime.engine.records()
  else records.value = []
  const next: Record<string, State> = {}, checks: Record<string, boolean> = {}
  for (const row of reviews.value) {
    const key = row.id + ':' + row.heads.join(',')
    next[key] = resolutions.value[key] ?? { ...row.variants[0]!.state }; checks[key] = Boolean(confirmed.value[key])
  }
  resolutions.value = next; confirmed.value = checks
}
async function perform(action: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (reason) { error.value = message(reason) }
  finally { busy.value = false; syncing.value = runtime.engine.syncing }
}
function activity() {
  lastActivity = Date.now()
  clearTimeout(inactivity)
  if (runtime.engine.unlocked) inactivity = setTimeout(lock, 5 * 60_000)
}
function lock() {
  clearTimeout(debounce); clearTimeout(inactivity); runtime.engine.lock(); runtime.auth.clear()
  unlocked.value = false; connected.value = false; records.value = []; selected.value = null; draft.value = {}; editing.value = false
  resolutions.value = {}; confirmed.value = {}; passphrase.value = ''; confirmation.value = ''; recovery.value = ''; pending.value = null; conflicts.value = null
  scanned.value = false
}
async function connectIdentity() {
  if (configuredClient !== clientId.value.trim()) { runtime.engine.lock(); runtime.auth.clear(); configuredClient = clientId.value.trim(); runtime = createRuntime(store, configuredClient) }
  const identity = await runtime.auth.connect(accountHint.value ? { prompt: '', loginHint: accountHint.value } : undefined), meta = await store.metadata()
  if (meta && identity.subject !== meta.subject) { runtime.auth.clear(); throw new Error('Choose the Google account used when pairing this workspace.') }
  connected.value = true; email.value = identity.email; notice.value = 'Google connected for this session. Access tokens stay in memory.'
}
function connect() { return perform(async () => {
  await connectIdentity()
  if (runtime.engine.unlocked) { await runtime.engine.sync(true); await refresh(); notice.value = 'Two-way sync is ready.' }
}) }
async function enroll() {
  try {
    if (passphrase.value.length < 12 || passphrase.value.length > 1024) throw new Error('Use an unlock passphrase of at least 12 characters')
    if (passphrase.value !== confirmation.value) throw new Error('The unlock passphrases do not match.')
    const identity = runtime.auth.identity(); if (!identity) throw new Error('Connect Google before pairing.')
    await runtime.engine.pair(recovery.value, passphrase.value, identity, clientId.value.trim())
    recovery.value = ''; await refresh(); activity(); notice.value = 'Paired. Sync now to download your workspace.'
    navigator.storage?.persist?.().catch(() => false)
  } finally { passphrase.value = ''; confirmation.value = '' }
}
function pair() { return perform(enroll) }
function connectAndPair() { return perform(async () => {
  try {
    // Validate before requesting a popup; no enrollment until verified Google identity.
    if (passphrase.value.length < 12 || passphrase.value.length > 1024) throw new Error('Use an unlock passphrase of at least 12 characters')
    if (passphrase.value !== confirmation.value) throw new Error('The unlock passphrases do not match.')
    if (!connected.value) await connectIdentity()
    await enroll(); scanned.value = false
    await runtime.engine.sync(true); await refresh(); notice.value = 'Phone connected. Two-way sync is ready.'
  } finally { passphrase.value = ''; confirmation.value = '' }
}) }
function unlock() { return perform(async () => {
  try { await runtime.engine.unlock(passphrase.value); await refresh(); activity(); notice.value = 'Unlocked locally. You can edit offline.' }
  finally { passphrase.value = '' }
}) }
async function sync(manual = true) {
  if (!runtime.engine.unlocked || runtime.engine.syncing) return
  syncing.value = true; error.value = ''
  try { await runtime.engine.sync(manual); await refresh(); notice.value = 'Sync completed.' }
  catch (reason) { if (runtime.engine.unlocked) { await refresh(); error.value ||= message(reason) } }
  finally { syncing.value = false; if (!runtime.auth.identity()) connected.value = false }
}
function resumed() {
  if (document.visibilityState !== 'visible' || !runtime.engine.unlocked) return
  if (Date.now() - lastActivity >= 5 * 60_000) { lock(); return }
  if (connected.value) void sync(false)
}
function saveSoon() { clearTimeout(debounce); if (connected.value) debounce = setTimeout(() => { if (document.visibilityState === 'visible') void sync(false) }, 3000) }
function newRecord() {
  selected.value = null; editing.value = true; reviewed.value = false
  const parent = applications.value[0]?.entityId ?? ''
  const defaults: Record<Entity, State> = {
    application: { company: '', job_title: '', date_applied: new Date().toISOString().slice(0, 10), job_url: '', email_reference: null, status: 'SUBMITTED', outcome: null, deleted: false },
    task: { application_id: parent, title: '', status: 'PENDING', due_at: null, completed_at: null, deleted: false },
    interview: { application_id: parent, scheduled_at: '', type: 'HR', duration: null, deleted: false },
    followup: { application_id: parent, sequence_number: Math.max(0, ...records.value.filter(row => row.entity === 'followup' && row.state.application_id === parent).map(row => Number(row.state.sequence_number))) + 1,
      due_at: '', status: 'PREPARED', sent_at: null, archived_at: null, snoozed_until: null, parent_followup_id: null, is_automatic: false, deleted: false },
  }
  draft.value = defaults[entity.value]
}
function edit(row: RecordState) { selected.value = JSON.parse(JSON.stringify(row)); entity.value = row.entity; draft.value = { ...row.state }; editing.value = true; reviewed.value = false }
function save() { return perform(async () => {
  if (entity.value === 'followup' && draft.value.status === 'SENT' && !reviewed.value) throw new Error('Confirm that this message was actually sent before recording SENT.')
  await runtime.engine.edit(entity.value, selected.value?.entityId ?? crypto.randomUUID(), draft.value, selected.value?.heads ?? [])
  editing.value = false; draft.value = {}; selected.value = null; await refresh(); activity(); saveSoon(); notice.value = 'Saved on this phone. Pending edits survive closing the app.'
}) }
function resolutionKey(row: RecordState) { return row.id + ':' + row.heads.join(',') }
function resolve(row: RecordState) { return perform(async () => {
  const key = resolutionKey(row); if (!confirmed.value[key]) return
  await runtime.engine.edit(row.entity, row.entityId, resolutions.value[key]!, row.heads, true)
  await refresh(); activity(); saveSoon(); notice.value = 'Reviewed resolution saved locally.'
}) }
function selectResolution(row: RecordState, field: string, event: Event) {
  const key = resolutionKey(row); resolutions.value[key]![field] = JSON.parse((event.target as HTMLSelectElement).value); confirmed.value[key] = false
}
function title(row: RecordState) { return String(row.state.company ?? row.state.title ?? (row.entity === 'interview' ? row.state.type : 'Follow-up ' + row.state.sequence_number)) }
function setOptional(field: string, event: Event, number = false) { const value = (event.target as HTMLInputElement).value; draft.value[field] = value ? number ? Number(value) : value : null }
function localDate(value: State[string] | undefined) {
  if (!value) return ''
  const date = new Date(String(value)); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}
function setDate(field: string, event: Event) { const value = (event.target as HTMLInputElement).value; draft.value[field] = value ? new Date(value).toISOString() : null }
watch(() => [draft.value.status, draft.value.sent_at], () => { reviewed.value = false })
function shellStatus() { ready.value = navigator.serviceWorker?.controller?.scriptURL.endsWith('/phone/sw.js') ?? false }
onMounted(async () => {
  if (!window.isSecureContext || !globalThis.indexedDB || !globalThis.crypto?.subtle || !globalThis.CompressionStream || !globalThis.DecompressionStream) {
    supported.value = false; error.value = 'This phone app needs HTTPS, IndexedDB, Web Crypto and gzip streams. Open it in a current Android Chrome or iPhone Safari browser with browser storage enabled.'; return
  }
  try {
    const meta = await store.metadata(); if (meta) { recovery.value = ''; scanned.value = false; clientId.value = meta.clientId; configuredClient = meta.clientId; email.value = meta.email; accountHint.value = meta.email; runtime = createRuntime(store, meta.clientId) }
    await refresh(); if (props.pairingError) error.value = props.pairingError
    if ('serviceWorker' in navigator) { navigator.serviceWorker.addEventListener('controllerchange', shellStatus); await navigator.serviceWorker.register('/phone/sw.js', { scope: '/phone/' }); shellStatus() }
  } catch (reason) { error.value = message(reason) }
  if (navigator.onLine) void runtime.preload().catch(() => {})
  window.addEventListener('online', resumed); window.addEventListener('pagehide', lock); window.addEventListener('pageshow', shellStatus)
  document.addEventListener('visibilitychange', resumed); document.addEventListener('pointerdown', activity); document.addEventListener('keydown', activity)
  poll = setInterval(resumed, 5 * 60_000)
})
onBeforeUnmount(() => {
  lock(); store.close(); clearInterval(poll)
  window.removeEventListener('online', resumed); window.removeEventListener('pagehide', lock); window.removeEventListener('pageshow', shellStatus)
  document.removeEventListener('visibilitychange', resumed); document.removeEventListener('pointerdown', activity); document.removeEventListener('keydown', activity)
  navigator.serviceWorker?.removeEventListener('controllerchange', shellStatus)
})
</script>
<template>
  <main>
    <header><div><p class="eyebrow">APPLICATION TRACKER</p><h1>Your phone workspace</h1></div><button v-if="unlocked" @click="lock">Lock</button></header>
    <p class="intro">Keep application summaries and work on this phone. Encrypted changes travel through Google Drive when you sync.</p>
    <p class="shell" role="status">{{ ready ? 'Offline app installed. Add this page to your home screen.' : 'Preparing the offline app. Keep this page open until installation completes.' }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <section v-if="supported && !paired && !scanned"><h2>Scan your desktop QR</h2><p>On desktop, open Settings → Phone and press Pair phone. Scan its private QR to connect automatically. If you just finished the private site's sign-in, scan that QR again.</p></section>
    <component :is="!paired && !scanned ? 'details' : 'div'">
    <summary v-if="!paired && !scanned">Advanced manual recovery</summary>
    <section v-if="supported && !scanned && (!paired || (unlocked && !connected))"><h2>{{ paired ? 'Google connection' : 'Pair with desktop' }}</h2>
      <p v-if="!paired">On desktop, press Pair phone and scan the private QR. Advanced recovery setup is available below.</p>
      <details><summary>Advanced connection settings</summary><label>Phone Web OAuth public client ID<input v-model="clientId" :readonly="paired" autocomplete="off" spellcheck="false" /></label></details>
      <button :disabled="busy || !clientId.trim()" @click="connect">{{ paired ? 'Connect and sync' : 'Connect Google for sync' }}</button>
      <p>Use the same Google account as desktop. The Web client must be in the same Google Cloud project and allow this page’s HTTPS origin. Each device authorizes independently.</p>
    </section>
    <section v-if="supported && !paired"><h2 v-if="scanned">Connect this phone</h2><p v-if="scanned">Desktop found · {{ accountHint }}. Choose an offline passphrase, then connect. Google handles account approval.</p><form @submit.prevent="scanned ? connectAndPair() : pair()"><label v-if="!scanned">Desktop recovery export<input v-model="recovery" type="password" autocomplete="off" spellcheck="false" required /></label><label>Choose an offline unlock passphrase<input v-model="passphrase" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required /></label><label>Confirm unlock passphrase<input v-model="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required /></label><button :disabled="busy || (!scanned && !connected)">{{ scanned ? (busy ? 'Connecting…' : 'Connect and sync') : 'Pair this phone' }}</button></form><p>The passphrase protects encrypted browser storage. Keep your recovery export separately; Google sign-in cannot replace it.</p></section>
    <section v-else-if="supported && !unlocked"><h2>Unlock offline</h2><p>{{ email }}</p><form @submit.prevent="unlock"><label>Offline unlock passphrase<input v-model="passphrase" type="password" autocomplete="current-password" required minlength="12" maxlength="1024" /></label><button :disabled="busy">Unlock this phone</button></form><p>No internet connection or desktop is needed to unlock previously downloaded records.</p></section>
    </component>
    <template v-if="unlocked">
      <section aria-label="Sync status"><h2>Sync status</h2><p>{{ email }}</p><p aria-live="polite">{{ pending }} waiting to upload · {{ conflicts }} records awaiting review or dependencies</p><p>{{ lastSuccess ? 'Last completed: ' + new Date(lastSuccess).toLocaleString() : 'No completed sync yet' }}</p><button :disabled="busy || syncing || !connected" @click="sync(true)">{{ syncing ? 'Syncing… Local edits remain available' : 'Sync now' }}</button><button :disabled="busy" @click="perform(refresh)">Refresh local view</button><p>Sync runs while this app is open and unlocked. Closing the app preserves pending changes. This phone locks after five minutes without activity.</p></section>
      <section><h2>Applications and work</h2><p>Documents, contacts, notes and message content stay on their device. Follow-up state does not approve or send a message here.</p><div class="new"><label>New record type<select v-model="entity" @change="editing = false"><option value="application">Application</option><option value="task">Task</option><option value="interview">Interview</option><option value="followup">Follow-up</option></select></label><button :disabled="busy || (entity !== 'application' && !applications.length)" @click="newRecord">Add record</button></div>
        <form v-if="editing" @submit.prevent="save" class="editor"><h3>{{ selected ? 'Edit' : 'Add' }} {{ entity }}</h3>
          <template v-if="entity === 'application'"><label>Company<input v-model="draft.company" required maxlength="300" /></label><label>Job title<input v-model="draft.job_title" required maxlength="300" /></label><label>Date applied<input v-model="draft.date_applied" type="date" required /></label><label>Job URL<input :value="draft.job_url ?? ''" type="url" maxlength="2048" @input="setOptional('job_url', $event)" /></label><label>Email reference<input :value="draft.email_reference ?? ''" maxlength="2048" @input="setOptional('email_reference', $event)" /></label><label>Status<select v-model="draft.status"><option>SUBMITTED</option><option>INTERVIEW</option><option>CLOSED</option></select></label><label>Outcome<select v-model="draft.outcome"><option :value="null">None</option><option>SUCCESSFUL</option><option>UNSUCCESSFUL</option><option>WITHDRAWN</option><option>JOB_CANCELLED</option><option>GHOSTED</option></select></label></template>
          <template v-else><label>Application<select v-model="draft.application_id" :disabled="Boolean(selected)" required><option v-for="parent in applications" :key="parent.id" :value="parent.entityId">{{ parent.state.company }} · {{ parent.state.job_title }}</option></select></label>
            <template v-if="entity === 'task'"><label>Task title<input v-model="draft.title" maxlength="300" required /></label><label>Task status<select v-model="draft.status"><option>PENDING</option><option>COMPLETED</option><option>CANCELLED</option></select></label><label>Due at<input :value="localDate(draft.due_at)" type="datetime-local" @input="setDate('due_at', $event)" /></label><label>Completed at<input :value="localDate(draft.completed_at)" type="datetime-local" @input="setDate('completed_at', $event)" /></label></template>
            <template v-if="entity === 'interview'"><label>Scheduled at<input :value="localDate(draft.scheduled_at)" type="datetime-local" required @input="setDate('scheduled_at', $event)" /></label><label>Interview type<select v-model="draft.type"><option>PHONE</option><option>HR</option><option>TECHNICAL</option><option>ONSITE</option><option>FINAL</option><option>OTHER</option></select></label><label>Duration in minutes<input :value="draft.duration ?? ''" type="number" min="1" @input="setOptional('duration', $event, true)" /></label></template>
            <template v-if="entity === 'followup'"><label>Sequence number<input v-model.number="draft.sequence_number" type="number" min="1" required /></label><label>Due at<input :value="localDate(draft.due_at)" type="datetime-local" required @input="setDate('due_at', $event)" /></label><label>Follow-up status<select v-model="draft.status"><option>PREPARED</option><option>READY</option><option>SENT</option></select></label><label>Actually sent at<input :value="localDate(draft.sent_at)" type="datetime-local" @input="setDate('sent_at', $event)" /></label><label v-if="draft.status === 'SENT'" class="check"><input v-model="reviewed" type="checkbox" /> I confirm this follow-up was actually sent outside this app.</label></template>
          </template>
          <label v-if="selected" class="check"><input v-model="draft.deleted" type="checkbox" /> Mark this record deleted after saving</label><div class="actions"><button :disabled="busy">Save on this phone</button><button type="button" @click="editing = false">Cancel</button></div>
        </form>
        <p v-if="!visible.length">No downloaded records yet. Connect Google and sync.</p><ul class="records"><li v-for="row in visible" :key="row.id"><div><strong>{{ title(row) }}</strong><p>{{ row.entity }} · {{ row.state.job_title ?? row.state.status ?? row.state.scheduled_at }}<span v-if="row.reason"> · Needs review</span></p></div><button :disabled="busy" @click="edit(row)">Edit {{ row.entity }}</button></li></ul>
      </section>
      <section v-for="row in reviews" :key="resolutionKey(row)" class="conflict"><h2>Review {{ row.entity }} conflict</h2><p>{{ row.reason?.replaceAll('_', ' ') }}</p><details><summary>Common ancestor and device proposals</summary><pre>{{ row.base }}</pre><pre v-for="variant in row.variants" :key="variant.head">{{ variant }}</pre></details><label v-for="(_, field) in resolutions[resolutionKey(row)]" :key="field">{{ String(field).replaceAll('_', ' ') }}<select :value="JSON.stringify(resolutions[resolutionKey(row)]![field])" @change="selectResolution(row, String(field), $event)"><option v-if="field in row.base" :value="JSON.stringify(row.base[field])">{{ row.base[field] ?? 'Empty' }} · common ancestor</option><option v-for="variant in row.variants" :key="variant.head" :value="JSON.stringify(variant.state[field])">{{ variant.state[field] ?? 'Empty' }} · {{ variant.device_id.slice(0, 8) }}</option></select><input v-if="field === 'sequence_number'" v-model.number="resolutions[resolutionKey(row)]![field]" aria-label="Reviewed sequence number" type="number" min="1" @input="confirmed[resolutionKey(row)] = false" /></label><label class="check"><input v-model="confirmed[resolutionKey(row)]" type="checkbox" /> I reviewed these values and their follow-up implications.</label><button :disabled="busy || !confirmed[resolutionKey(row)]" @click="resolve(row)">Save reviewed resolution</button></section>
    </template>
    <footer><p>Keep a separate desktop backup and recovery export. Browser storage can be cleared by the browser or device owner. Only compressed record changes use Drive storage; documents and message bodies stay on their device.</p></footer>
  </main>
</template>
<style>
:root{font-family:system-ui,sans-serif;color:#24352f;background:#f7f6f2;font-size:16px;color-scheme:light}*{box-sizing:border-box}body{margin:0}main{max-width:860px;margin:auto;padding:24px 16px 64px}header,.actions,.new{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}h1{font-size:28px;margin:4px 0 16px}h2{font-size:21px}h3{font-size:18px}.eyebrow{font-size:12px;letter-spacing:.12em;font-weight:700;color:#1c5b53;margin:8px 0}p{line-height:1.6;overflow-wrap:anywhere}.intro{max-width:48em}section{background:#fffefb;border:1px solid #b5bdb3;border-radius:12px;padding:20px;margin:18px 0}label{display:block;font-weight:600;margin:14px 0 6px}input,select,button{font:inherit;min-height:46px;border-radius:6px;border:1px solid #87998f;padding:10px;background:#fffefb;color:#24352f}input,select{display:block;width:100%;margin-top:6px;min-width:0}button{cursor:pointer;background:#1c5b53;color:white;padding:11px 16px}button:disabled{opacity:.6;cursor:default}.check{display:flex;align-items:center;gap:10px;font-weight:400}.check input{width:22px;flex-shrink:0;margin:0}input:focus-visible,select:focus-visible,button:focus-visible,a:focus-visible{outline:3px solid #347f75;outline-offset:3px}.error{background:#fff0ee;color:#882521;padding:14px;border:1px solid #be5850;border-radius:8px}.notice,.shell{background:#edf4ee;padding:12px;border-radius:8px}.records{padding:0;list-style:none}.records li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0;border-bottom:1px solid #d3d9d1}.records li div{min-width:0;overflow-wrap:anywhere}.records li p{margin:4px 0}.records button{flex-shrink:0}.editor{border-top:1px solid #b5bdb3;margin-top:18px;padding-top:12px}.conflict{border-color:#9c6c22}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%;font-size:12px}a{color:#1b625b}@media(max-width:480px){main{padding:14px 10px 48px}section{padding:16px}h1{font-size:25px}.records li{align-items:flex-start;flex-direction:column}.records button{width:100%}.new{align-items:stretch}.new label{flex:1;margin:0}.new button{align-self:end}}
</style>
