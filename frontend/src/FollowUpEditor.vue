<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Button from 'primevue/button'
import TemplateField from './components/shared/TemplateField.vue'
import DateTimeField from './components/shared/DateTimeField.vue'
import { updateFollowUp, updateApplication, getTemplateVariables, getFollowUpAIRequest, proposeFollowUp, applyFollowUpTemplate, createNote, undoLastChange, type FollowUp, type Application, type FollowUpChanges, type TemplateVariable, type MessageProposal } from './api'
const props = defineProps<{ item: FollowUp; application: Application }>()
const emit = defineEmits<{ changed: [] }>()
const variables = ref<TemplateVariable[]>([])
const form = reactive({ subject: '', body: '', instructions: '', language: '', tone: '', signature: '' })
const job = reactive({ instructions: '', language: '', tone: '', signature: '' })
let savedJobForm = ''
const dueAt = ref('')
const sentAt = ref('')
const snoozeAt = ref('')
const note = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const copyFallback = ref('')
const proposal = ref<MessageProposal | null>(null)
const proposalLatest = ref(true)
const dirty = computed(() => form.subject !== props.item.subject || form.body !== props.item.body || form.instructions !== props.item.instructions || form.language !== (props.item.customization.language ?? '') || form.tone !== (props.item.customization.tone ?? '') || form.signature !== (props.item.customization.signature ?? ''))
const unresolved = computed(() => [...new Set([...(form.subject + '\n' + form.body).matchAll(/\{([^{}\n]+)\}/g)].map(m => m[1]))])
function localTime(value: string | null) { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
function reset() {
  const preserveJobEdits = savedJobForm !== '' && JSON.stringify(job) !== savedJobForm
  Object.assign(form, { subject: props.item.subject, body: props.item.body, instructions: props.item.instructions, language: props.item.customization.language ?? '', tone: props.item.customization.tone ?? '', signature: props.item.customization.signature ?? '' })
  const jobDefaults = { instructions: props.application.followup_instructions ?? '', language: props.application.followup_customization?.language ?? '', tone: props.application.followup_customization?.tone ?? '', signature: props.application.followup_customization?.signature ?? '' }
  if (!preserveJobEdits) Object.assign(job, jobDefaults)
  savedJobForm = JSON.stringify(jobDefaults)
  dueAt.value = localTime(props.item.due_at); sentAt.value = localTime(props.item.sent_at ?? new Date().toISOString()); snoozeAt.value = localTime(props.item.snoozed_until); proposal.value = null
}
watch(() => props.item, reset, { immediate: true })
async function perform(action: () => Promise<unknown>, message: string, saveEdits = false) {
  if (busy.value) return
  if (dirty.value && !saveEdits) { error.value = 'Save your message edits before changing another setting.'; return }
  busy.value = true; error.value = ''; notice.value = ''
  try { await action(); notice.value = message; emit('changed') }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to save. Your entries are retained.' }
  finally { busy.value = false }
}
function save() { return perform(() => updateFollowUp(props.application.id, props.item.id, { subject: form.subject, body: form.body, instructions: form.instructions, customization: { language: form.language || null, tone: form.tone || null, signature: form.signature || null }, expected_revision: props.item.revision }), 'Message saved. It has not been sent.', true) }
function change(data: FollowUpChanges, message: string) { return perform(() => updateFollowUp(props.application.id, props.item.id, { ...data, expected_revision: props.item.revision }), message) }
async function copy(text: string, label: string, allowTags = false) {
  error.value = ''; copyFallback.value = ''
  if (!allowTags && /\{[^{}\n]+\}/.test(text)) { error.value = 'Fill or remove the highlighted variables and save before copying.'; return }
  try { await navigator.clipboard.writeText(text); notice.value = `${label} copied. Nothing was sent.` }
  catch { copyFallback.value = text; notice.value = 'Clipboard access is unavailable. Select and copy the text below.' }
}
async function copyAI() {
  try { await copy(JSON.stringify(await getFollowUpAIRequest(props.application.id, props.item.id), null, 2), 'AI instructions', true) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to prepare AI instructions.' }
}
async function propose(latest: boolean) {
  error.value = ''; proposalLatest.value = latest
  try { proposal.value = await proposeFollowUp(props.application.id, props.item.id, latest) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to prepare replacement.' }
}
function apply() {
  if (!proposal.value) return
  return perform(() => applyFollowUpTemplate(props.application.id, props.item.id, proposal.value!.expected_revision, proposalLatest.value), 'Replacement applied. Review the message before marking ready.')
}
onMounted(async () => { try { variables.value = await getTemplateVariables() } catch { error.value = 'Unable to load template variables.' } })
</script>

<template>
  <section class="editor" :aria-busy="busy"><div class="heading"><div><h3>{{ application.company }} · {{ application.job_title }}</h3><p>Follow-up #{{ item.sequence_number }} · {{ item.status === 'SENT' && item.channel === 'PHONE' ? 'Completed' : item.status.toLowerCase() }}<span v-if="item.archived_at"> · archived</span><span v-if="application.followup_paused"> · reminders paused</span></p></div><a :href="`#/applications/${application.id}`">Application and notes</a></div>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <p v-if="item.channel === 'PHONE'">Phone follow-up · {{ application.phone_number }}. Record completion after making the call.</p>
    <p v-if="item.status !== 'SENT' && !item.archived_at && !application.followup_paused && application.status !== 'CLOSED'"><a :href="`/api/applications/${application.id}/followups/${item.id}/calendar.ics`" download>Download calendar reminder</a> · Import it into your calendar as an optional reminder. Re-export after changing its date.</p>
    <form v-if="item.channel !== 'PHONE'" @submit.prevent="save"><fieldset :disabled="busy || item.status === 'SENT' || !!item.archived_at"><legend class="sr-only">Prepared follow-up</legend>
      <TemplateField v-model="form.subject" label="Follow-up subject" :variables="variables" :rows="2" :disabled="busy || item.status === 'SENT' || !!item.archived_at" />
      <TemplateField v-model="form.body" label="Follow-up message" :variables="variables" :rows="10" :disabled="busy || item.status === 'SENT' || !!item.archived_at" />
      <label>Instructions for this follow-up<textarea v-model="form.instructions" rows="3" maxlength="12000" /></label>
      <details><summary>Customize this message</summary><p>Blank values inherit job preferences and the saved default template preferences.</p><div class="grid"><label>Language<input v-model="form.language" maxlength="80" /></label><label>Tone<input v-model="form.tone" maxlength="120" /></label></div><label>Signature override<textarea v-model="form.signature" rows="2" maxlength="3000" /></label></details>
      <p v-if="unresolved.length" class="at-message warning">Highlighted variables resolve when you save if the data is available. Otherwise fill or remove them: {{ unresolved.join(', ') }}</p>
      <div class="actions"><Button type="submit" :disabled="busy || !dirty">Save message</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="propose(true)">Preview latest template</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="propose(false)">Preview refreshed variables</Button></div>
    </fieldset></form>
    <div v-if="proposal" class="proposal"><h4>Review replacement</h4><p>Your existing edits will be replaced only if you apply this preview.</p><strong>{{ proposal.subject.text }}</strong><pre>{{ proposal.body.text }}</pre><div class="actions"><Button type="button" :disabled="busy" @click="apply">Apply replacement</Button><Button type="button" severity="secondary" @click="proposal = null">Keep existing message</Button></div></div>
    <div class="actions"><Button v-if="item.channel !== 'PHONE'" type="button" :disabled="busy || dirty" @click="copy(item.subject, 'Subject')">Copy subject</Button><Button v-if="item.channel !== 'PHONE'" type="button" :disabled="busy || dirty" @click="copy(item.body, 'Message')">Copy message</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="copyAI">Copy AI instructions</Button><Button v-if="item.status === 'PREPARED' && !item.archived_at" type="button" :disabled="busy || dirty || !!unresolved.length" @click="change({ status: 'READY' }, 'Message marked ready. Send it from your mail client.')">Mark ready</Button><Button v-if="item.status === 'READY'" type="button" severity="secondary" :disabled="busy" @click="change({ status: 'PREPARED' }, 'Returned to prepared.')">Return to prepared</Button></div>
    <label v-if="copyFallback">Select and copy<textarea :value="copyFallback" rows="6" readonly @focus="($event.target as HTMLTextAreaElement).select()" /></label>
    <div v-if="!item.archived_at" class="grid"><div><DateTimeField v-model="sentAt" :label="item.status === 'SENT' ? 'Actual sent time (local)' : 'Sent or completed at (local)'" :disabled="busy" /><Button type="button" :disabled="busy || dirty || !sentAt" @click="change({ status: 'SENT', sent_at: new Date(sentAt).toISOString() }, 'Actual send recorded in the tracker.')">{{ item.status === 'SENT' ? 'Correct sent time' : item.channel === 'PHONE' ? 'Record completed call' : 'Record already sent' }}</Button></div><div v-if="item.status !== 'SENT'"><DateTimeField v-model="dueAt" label="Follow-up due (local)" :disabled="busy" /><Button type="button" :disabled="busy || !dueAt" @click="change({ due_at: new Date(dueAt).toISOString() }, 'Follow-up rescheduled.')">Reschedule</Button></div></div>
    <details><summary>Reminder controls and job instructions</summary><div v-if="item.status !== 'SENT'" class="grid"><div><DateTimeField v-model="snoozeAt" label="Snooze reminder until (local)" :disabled="busy" /><div class="actions"><Button type="button" :disabled="busy || !snoozeAt" @click="change({ snoozed_until: new Date(snoozeAt).toISOString() }, 'Reminder snoozed. The due date is unchanged.')">Snooze</Button><Button type="button" severity="secondary" :disabled="busy" @click="change({ snoozed_until: null }, 'Snooze cleared.')">Clear snooze</Button></div></div><div class="actions"><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => updateApplication(application.id, { followup_paused: !application.followup_paused }), application.followup_paused ? 'Job reminders resumed.' : 'Job reminders paused.')">{{ application.followup_paused ? 'Resume job reminders' : 'Pause job reminders' }}</Button></div></div>
      <label>Instructions for this job<textarea v-model="job.instructions" rows="3" maxlength="12000" /></label><div class="grid"><label>Job language override<input v-model="job.language" maxlength="80" /></label><label>Job tone override<input v-model="job.tone" maxlength="120" /></label></div><label>Job signature override<textarea v-model="job.signature" rows="2" maxlength="3000" /></label><Button type="button" :disabled="busy" @click="perform(() => updateApplication(application.id, { followup_instructions: job.instructions, followup_customization: { language: job.language || null, tone: job.tone || null, signature: job.signature || null } }), 'Job preferences saved. Unsent messages require review again.')">Save job preferences</Button>
      <div class="actions"><Button type="button" severity="secondary" :disabled="busy" @click="change({ archived: !item.archived_at }, item.archived_at ? 'Follow-up restored.' : 'Follow-up archived.')">{{ item.archived_at ? 'Restore follow-up' : 'Archive follow-up' }}</Button><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => undoLastChange(application.id), 'Last change undone.')">Undo last change</Button></div>
    </details>
    <label>Add a note<textarea v-model="note" rows="3" placeholder="Record a reply or anything to remember." /></label><Button type="button" :disabled="busy || !note.trim()" @click="perform(async () => { await createNote(application.id, { content: note, type: 'GENERAL' }); note = '' }, 'Note added.')">Save note</Button>
  </section>
</template>

<style scoped>
.editor{padding:22px;background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;margin:18px 0}.heading{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.heading p,details p{color:var(--at-text-muted)}fieldset{padding:0;border:0;margin:0}label{display:block;font-weight:600;margin:12px 0}input,textarea{box-sizing:border-box;width:100%;font:inherit;margin-top:6px;padding:10px;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.proposal{padding:16px;border:1px solid var(--at-primary);border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}summary{cursor:pointer;font-weight:600;margin:18px 0}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:650px){.grid{grid-template-columns:1fr}.heading{flex-direction:column}.editor{padding:14px}}
</style>
