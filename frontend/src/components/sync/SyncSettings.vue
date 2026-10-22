<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import { syncClient, type SyncStatus, type SyncConflict, type CompactState } from '../../syncClient'

defineProps<{ driveReady: boolean }>()
const status = ref<SyncStatus | null>(null)
const conflicts = ref<SyncConflict[]>([])
const choices = ref<Record<string, CompactState>>({})
const label = ref('Desktop')
const pairing = ref('')
const recovery = ref('')
const consent = ref(false)
const confirmed = ref<Record<string, boolean>>({})
const busy = ref(false)
const error = ref('')
async function load() {
  status.value = await syncClient.status()
  conflicts.value = status.value.conflicts ? await syncClient.conflicts() : []
  const nextChoices: Record<string, CompactState> = {}
  const nextConfirmed: Record<string, boolean> = {}
  for (const conflict of conflicts.value) {
    nextChoices[conflict.id] = choices.value[conflict.id] ?? { ...conflict.variants[0]?.state }
    nextConfirmed[conflict.id] = Boolean(choices.value[conflict.id] && confirmed.value[conflict.id])
  }
  choices.value = nextChoices; confirmed.value = nextConfirmed
}
async function perform(action: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await action() } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Sync failed.' }
  finally { busy.value = false }
}
function initialize() { return perform(async () => {
  if (!consent.value) return
  const result = await syncClient.initialize(label.value.trim(), pairing.value.trim() || null)
  recovery.value = result.recovery_export; pairing.value = ''; consent.value = false
  await load()
}) }
function run() { return perform(async () => { status.value = await syncClient.run(); await load() }) }
function resolve(conflict: SyncConflict) { return perform(async () => {
  if (!confirmed.value[conflict.id]) return
  await syncClient.resolve(conflict, choices.value[conflict.id]!)
  confirmed.value[conflict.id] = false
  await load()
}) }
function selectValue(conflict: SyncConflict, field: string, event: Event) {
  choices.value[conflict.id]![field] = JSON.parse((event.target as HTMLSelectElement).value)
  confirmed.value[conflict.id] = false
}
function formatTimestamp(value: string) { return new Date(value).toLocaleString() }
onMounted(() => perform(load))
</script>

<template>
  <section class="sync-panel" aria-labelledby="compact-sync-title">
    <h3 id="compact-sync-title">Encrypted compact sync</h3>
    <p>Synchronize application summaries, tasks, interview schedules and follow-up state through your Google account. Documents, notes, contacts, message content and Google credentials stay on their device.</p>
    <p v-if="!driveReady">Connect Google with Drive app data permission to enable sync.</p>
    <form v-if="status && (!status.initialized || status.recovery_required)" @submit.prevent="initialize">
      <label>Device name <input v-model="label" maxlength="100" required /></label>
      <label>Recovery export from an existing device (leave empty to create a workspace)
        <input v-model="pairing" type="password" autocomplete="off" spellcheck="false" />
      </label>
      <label><input v-model="consent" type="checkbox" /> Store compact encrypted sync files in my Google account.</label>
      <Button type="submit" :disabled="busy || !driveReady || !consent || !label.trim()">{{ pairing ? 'Pair this device' : 'Initialize sync' }}</Button>
    </form>
    <div v-if="recovery" class="recovery" role="status">
      <p>Save this recovery export somewhere safe and separate from Google. It is shown for this setup only. Losing every device and this export means losing access to encrypted sync data.</p>
      <label>Recovery export <textarea :value="recovery" readonly rows="3" autocomplete="off" spellcheck="false" /></label>
      <Button type="button" severity="secondary" @click="recovery = ''">I saved it — hide</Button>
    </div>
    <template v-if="status?.initialized">
      <p><strong>{{ status.label }}</strong> · {{ status.last_success ? `Last completed check: ${formatTimestamp(status.last_success)}` : 'No completed sync yet' }}</p>
      <p v-if="status.running" role="status">Sync is running. Local edits remain saved; refresh this status to check progress.</p>
      <p aria-live="polite">{{ status.pending_uploads }} waiting to upload · {{ status.pending_downloads }} remote changes awaiting application · {{ status.conflicts }} records need review</p>
      <p>Drive usage: {{ ((status.remote_bytes ?? 0) / 1000000).toFixed(2) }} MB · {{ status.remote_objects ?? 0 }} observed files. Overall Google storage quota is unavailable.</p>
      <p v-if="status.error" role="alert">{{ status.error }}</p>
      <p v-for="warning in status.warnings" :key="warning" role="status">{{ warning }}</p>
      <Button type="button" :disabled="busy || !driveReady || status.recovery_required" @click="run">Sync now</Button>
      <Button type="button" severity="secondary" :disabled="busy" @click="perform(load)">Refresh sync status</Button>
      <details v-if="status.devices?.length"><summary>Devices observed in this workspace</summary>
        <p v-for="device in status.devices" :key="device.device_id">{{ device.device_id }} · last seen {{ formatTimestamp(device.last_seen) }}</p>
      </details>
      <article v-for="conflict in conflicts" :key="conflict.id" class="conflict">
        <h4>Review {{ conflict.record_key.split(':')[0] }} conflict</h4>
        <p>{{ conflict.record_key }} · {{ conflict.reason.replaceAll('_', ' ') }}</p>
        <p>Choose each final value. Status and outcome must agree. A resolution never sends mail or approves a message on this device.</p>
        <details><summary>Common ancestor and device proposals</summary>
          <pre>{{ conflict.base }}</pre>
          <div v-for="variant in conflict.variants" :key="variant.head"><p>{{ variant.device_id }} · reported actor {{ variant.actor }}</p><pre>{{ variant.state }}</pre></div>
        </details>
        <label v-for="(_, field) in choices[conflict.id]" :key="field">{{ String(field).replaceAll('_', ' ') }}
          <select :value="JSON.stringify(choices[conflict.id]![field])" @change="selectValue(conflict, String(field), $event)">
            <option v-if="field in conflict.base" :value="JSON.stringify(conflict.base[field])">{{ conflict.base[field] ?? 'Empty' }} · common ancestor</option>
            <option v-for="variant in conflict.variants" :key="variant.head" :value="JSON.stringify(variant.state[field])">{{ variant.state[field] ?? 'Empty' }} · {{ variant.device_id.slice(0, 8) }}</option>
          </select>
          <input v-if="field === 'sequence_number'" v-model.number="choices[conflict.id]![field]" type="number" min="1" aria-label="Reviewed follow-up sequence number" @input="confirmed[conflict.id] = false" />
        </label>
        <label><input v-model="confirmed[conflict.id]" type="checkbox" /> I reviewed the final values and their follow-up implications.</label>
        <Button type="button" :disabled="busy || !confirmed[conflict.id]" @click="resolve(conflict)">Save reviewed resolution</Button>
      </article>
    </template>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p>
    <p>Uploaded changes reach another device when it checks Drive. The independent offline phone client is not enabled yet. Compact sync does not replace portable backups; journal deletion is disabled.</p>
  </section>
</template>

<style scoped>
.sync-panel{margin-top:24px;padding-top:20px;border-top:1px solid var(--at-border)}p{line-height:1.5}label{display:block;margin:12px 0}input:not([type=checkbox]),textarea,select{display:block;width:100%;max-width:36em;padding:8px;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:4px}textarea{overflow-wrap:anywhere}button{margin:4px 8px 4px 0}.conflict,.recovery{padding:16px;margin:16px 0;border:1px solid var(--at-border);border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
</style>
