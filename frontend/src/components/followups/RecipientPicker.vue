<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import BusyIndicator from '../shared/BusyIndicator.vue'
import { chooseRecipient, fetchRecipients, getRecipientState, updateFollowUp, type FollowUp, type RecipientCandidate, type RecipientState } from '../../api'
const props = defineProps<{ applicationId: string; followup?: FollowUp; disabled?: boolean; closed?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const state = ref<RecipientState | null>(null)
const selected = ref('')
const email = ref('')
const name = ref('')
const error = ref('')
const notice = ref('')
const busy = ref(false)
const loading = ref(true)
let version = 0
let timer: ReturnType<typeof setInterval> | undefined
let disposed = false
const active = computed(() => ['QUEUED', 'RUNNING'].includes(state.value?.job?.state ?? ''))
const item = computed(() => state.value?.followups.find(f => f.id === (props.followup?.id ?? selected.value)))
const dirty = computed(() => email.value !== (item.value?.recipient_email ?? '') || name.value !== (item.value?.recipient_name ?? ''))
const blocked = computed(() => busy.value || props.disabled || props.closed)
const labels = { recruiter_hr: 'Recruiter / HR', technical_lead: 'Technical lead', general_contact: 'General company contact' }
function resetForm() { email.value = item.value?.recipient_email ?? ''; name.value = item.value?.recipient_name ?? '' }
async function load() {
  const current = ++version
  const keepEdits = dirty.value
  try {
    const result = await getRecipientState(props.applicationId)
    if (current !== version || disposed) return
    state.value = result
    if (!result.followups.some(f => f.id === selected.value)) selected.value = result.followups.find(f => !f.recipient_email)?.id ?? result.followups[0]?.id ?? ''
    if (!keepEdits) resetForm()
  } catch (reason) { if (current === version) error.value = reason instanceof Error ? reason.message : 'Unable to load recipients.' }
  finally { if (current === version) loading.value = false }
}
async function perform(action: () => Promise<unknown>, message: string, changed = false) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await action(); notice.value = message; await load(); if (changed) { resetForm(); emit('changed') } }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to save. Your entries are retained.' }
  finally { busy.value = false }
}
function queue() { return perform(() => fetchRecipients(props.applicationId), 'Recipient search queued. You can continue working.') }
function useCandidate(candidate: RecipientCandidate) {
  if (!item.value) return
  return perform(() => chooseRecipient(props.applicationId, item.value!.id, candidate.id, item.value!.revision), 'Recipient selected. Review the message before sending.', true)
}
function saveManual() {
  if (!item.value) return
  return perform(async () => { await updateFollowUp(props.applicationId, item.value!.id, { recipient_email: email.value.trim() || null, recipient_name: name.value.trim() || null, expected_revision: item.value!.revision }); }, 'Recipient saved. Nothing was sent.', true)
}
function sourceLink(value: string) { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? value : '' } catch { return '' } }
watch(() => [props.applicationId, props.followup?.revision], load, { immediate: true })
watch(selected, resetForm)
function invalidate(event: Event) { if ((event as CustomEvent).detail?.application_id === props.applicationId) void load() }
onMounted(() => { timer = setInterval(() => { if (active.value) void load() }, 2000); window.addEventListener('tracker:invalidate', invalidate) })
onUnmounted(() => { disposed = true; version++; clearInterval(timer); window.removeEventListener('tracker:invalidate', invalidate) })
</script>

<template>
  <section class="recipients" aria-label="Follow-up recipients">
    <div class="heading"><h3>Follow-up recipients</h3><Button type="button" severity="secondary" :disabled="blocked || active" @click="queue">{{ state?.job ? 'Fetch recipients again' : 'Fetch recipients' }}</Button></div>
    <p>Search public pages for this company and role, then choose a recipient. The search does not send email.</p>
    <BusyIndicator v-if="loading" label="Loading recipients…" />
    <BusyIndicator v-else-if="active" :label="state?.job?.state === 'QUEUED' ? 'Recipient search queued · up to five jobs run at once' : 'Finding recipients…'" />
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <p v-if="state?.missing_followups" class="at-message warning">{{ state.missing_followups }} email follow-up{{ state.missing_followups === 1 ? '' : 's' }} still need a recipient.</p>
    <p v-if="state?.job?.state === 'NO_RESULTS'">No suitable public recipient was found. Enter a known address or try again.</p>
    <p v-if="state?.job?.error" class="at-message warning">{{ state.job.error }}</p>
    <details v-if="state?.job?.warnings.length"><summary>Search limitations</summary><ul><li v-for="warning in state.job.warnings" :key="warning">{{ warning }}</li></ul></details>
    <label v-if="!followup && state?.followups.length">Choose follow-up<select v-model="selected" :disabled="blocked"><option v-for="f in state.followups" :key="f.id" :value="f.id">#{{ f.sequence_number }} · {{ f.recipient_email || 'Recipient needed' }}</option></select></label>
    <p v-if="item?.recipient_email">Selected recipient: <strong>{{ item.recipient_name || item.recipient_email }}</strong><span v-if="item.recipient_name"> · {{ item.recipient_email }}</span></p>
    <div class="candidates"><article v-for="candidate in state?.candidates ?? []" :key="candidate.id"><strong>{{ candidate.name || candidate.email }}</strong><p>{{ labels[candidate.kind] }}<span v-if="candidate.role"> · {{ candidate.role }}</span></p><p>{{ candidate.email || 'No public email found. Enter a confirmed address manually.' }}</p><p class="hint">{{ candidate.evidence }}</p><p><a v-if="sourceLink(candidate.source_url)" :href="sourceLink(candidate.source_url)" target="_blank" rel="noopener noreferrer">View source</a> · Vacancy responsibility unconfirmed<span v-if="candidate.stale"> · Older cached evidence</span><span v-if="!candidate.context_current"> · Job changed since this search</span></p><Button type="button" :disabled="blocked || dirty || !item || !candidate.email || !candidate.context_current" @click="useCandidate(candidate)">Use this recipient</Button></article></div>
    <form v-if="item" @submit.prevent="saveManual"><fieldset :disabled="blocked"><legend>Enter a recipient manually</legend><div class="grid"><label>Recipient email<input v-model="email" type="email" maxlength="320" placeholder="recruiter@company.com" /></label><label>Recipient name (optional)<input v-model="name" maxlength="300" /></label></div><Button type="submit" :disabled="blocked || !dirty">Save recipient</Button></fieldset></form>
    <p v-else-if="!loading">Create or reopen an email follow-up to assign a recipient.</p>
  </section>
</template>

<style scoped>
.recipients{padding:18px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface);margin:18px 0}.heading{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}.heading h3{margin:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;font-weight:600;margin:10px 0}input,select{display:block;width:100%;box-sizing:border-box;margin-top:6px;padding:9px;font:inherit;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}fieldset{border:0;padding:0;margin:16px 0}legend{font-weight:600}.candidates article{border-top:1px solid var(--at-border);padding:14px 0}p{overflow-wrap:anywhere}.hint{font-size:13px;color:var(--at-text-muted)}@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style>
