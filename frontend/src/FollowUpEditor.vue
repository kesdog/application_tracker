<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import SuggestionField from './components/shared/SuggestionField.vue'
import AIResults from './components/followups/AIResults.vue'
import RecipientPicker from './components/followups/RecipientPicker.vue'
import { followupLanguages } from './followupLanguages'
import Button from 'primevue/button'
import TemplateField from './components/shared/TemplateField.vue'
import DateTimeField from './components/shared/DateTimeField.vue'
import { getFollowUpAgentStatus, getRenderedFollowUp, queueFollowUpDraft, updateFollowUp, updateApplication, getTemplateVariables, getFollowUpAIRequest, proposeFollowUp, applyFollowUpTemplate, createNote, undoLastChange, type FollowUp, type Application, type FollowUpChanges, type TemplateVariable, type MessageProposal } from './api'
const props = defineProps<{ item: FollowUp; application: Application }>()
const emit = defineEmits<{ changed: [] }>()
const variables = ref<TemplateVariable[]>([])
const form = reactive({ subject: '', body: '', instructions: '', language: '', tone: '', signature: '' })
const job = reactive({ instructions: '', language: '', tone: '', signature: '' })
let savedJobForm = ''
const dueAt = ref('')
const snoozeAt = ref('')
const note = ref('')
const employerReply = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const copyFallback = ref('')
const proposal = ref<MessageProposal | null>(null)
const proposalLatest = ref(true)
const canDraft = ref(false)
const draftQueued = ref(false)
let queuedFollowupId = ''
let statusTimer: ReturnType<typeof setInterval> | undefined
let disposed = false
const languageSuggestions = computed(() => [...new Set([...followupLanguages, form.language, job.language, String(props.item.template_snapshot.language ?? '')].filter(Boolean))])
async function refreshAgent() {
  try { const status = await getFollowUpAgentStatus(); if (!disposed) canDraft.value = status.can_draft }
  catch { if (!disposed) canDraft.value = false }
}
function writeToDraft() {
  return perform(async () => { await queueFollowUpDraft(props.application.id, props.item.id, props.item.revision); queuedFollowupId = props.item.id; draftQueued.value = true }, 'Added to the AI task list. The agent can write it to a draft.', false)
}
async function copyResolved(field: 'subject' | 'body') {
  error.value = ''
  try {
    const rendered = await getRenderedFollowUp(props.application.id, props.item.id)
    if (rendered.revision !== props.item.revision) throw new Error('The message changed. Reload it before copying.')
    const text = rendered[field]
    if (text.missing.length || text.unknown.length) throw new Error(`Fill or remove these variables before copying: ${[...text.missing, ...text.unknown].join(', ')}`)
    await copy(text.text, field === 'subject' ? 'Subject' : 'Message', true)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to resolve message variables.' }
}
const dirty = computed(() => form.subject !== props.item.subject || form.body !== props.item.body || form.instructions !== props.item.instructions || form.language !== (props.item.customization.language ?? '') || form.tone !== (props.item.customization.tone ?? '') || form.signature !== (props.item.customization.signature ?? ''))
const unresolved = computed(() => [...new Set([...(form.subject + '\n' + form.body).matchAll(/\{([^{}\n]+)\}/g)].map(m => m[1]))])
function localTime(value: string | null) { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
function reset() {
  if (props.item.id !== queuedFollowupId) draftQueued.value = false
  const preserveJobEdits = savedJobForm !== '' && JSON.stringify(job) !== savedJobForm
  Object.assign(form, { subject: props.item.subject, body: props.item.body, instructions: props.item.instructions, language: props.item.customization.language ?? '', tone: props.item.customization.tone ?? '', signature: props.item.customization.signature ?? '' })
  const jobDefaults = { instructions: props.application.followup_instructions ?? '', language: props.application.followup_customization?.language ?? '', tone: props.application.followup_customization?.tone ?? '', signature: props.application.followup_customization?.signature ?? '' }
  if (!preserveJobEdits) Object.assign(job, jobDefaults)
  savedJobForm = JSON.stringify(jobDefaults)
  dueAt.value = localTime(props.item.due_at); snoozeAt.value = localTime(props.item.snoozed_until); proposal.value = null
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
  return perform(() => applyFollowUpTemplate(props.application.id, props.item.id, proposal.value!.expected_revision, proposalLatest.value), 'Replacement applied. Review the message before requesting a draft.')
}
onMounted(async () => { void refreshAgent(); statusTimer = setInterval(refreshAgent, 60000); window.addEventListener('focus', refreshAgent); try { variables.value = await getTemplateVariables() } catch { error.value = 'Unable to load template variables.' } })
onUnmounted(() => { disposed = true; clearInterval(statusTimer); window.removeEventListener('focus', refreshAgent) })
</script>

<template>
  <section class="editor" :aria-busy="busy"><div class="heading"><div><h3>{{ application.company }} · {{ application.job_title }}</h3><p>Follow-up #{{ item.sequence_number }} · {{ item.status === 'SENT' && item.channel === 'PHONE' ? 'Completed' : item.status.toLowerCase() }}<span v-if="item.archived_at"> · archived</span><span v-if="application.followup_paused"> · reminders paused</span></p></div><a :href="`#/applications/${application.id}`">Application and notes</a></div>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <p v-if="item.channel === 'PHONE'">Phone follow-up · {{ application.phone_number }}. Record completion after making the call.</p>
    <RecipientPicker v-if="item.channel !== 'PHONE' && item.status !== 'SENT' && !item.archived_at" :application-id="application.id" :followup="item" :disabled="busy || dirty" :closed="application.status === 'CLOSED'" @changed="emit('changed')" />
    <p v-if="item.status !== 'SENT' && !item.archived_at && !application.followup_paused && application.status !== 'CLOSED'"><a :href="`/api/applications/${application.id}/followups/${item.id}/calendar.ics`" download>Download calendar reminder</a> · Import it into your calendar as an optional reminder. Re-export after changing its date.</p>
    <form v-if="item.channel !== 'PHONE'" @submit.prevent="save"><fieldset :disabled="busy || item.status === 'SENT' || !!item.archived_at"><legend class="sr-only">Prepared follow-up</legend>
      <TemplateField v-model="form.subject" label="Follow-up subject" :variables="variables" :rows="2" :disabled="busy || item.status === 'SENT' || !!item.archived_at" />
      <TemplateField v-model="form.body" label="Follow-up message" :variables="variables" :rows="10" :disabled="busy || item.status === 'SENT' || !!item.archived_at" />
      <label>Instructions for this follow-up<textarea v-model="form.instructions" rows="3" maxlength="12000" /></label>
      <details><summary>Customize this message</summary><p>Blank values inherit job preferences and the saved default template preferences.</p><SuggestionField v-model="form.language" label="Language" :suggestions="languageSuggestions" :maxlength="80" :disabled="busy || item.status === 'SENT' || !!item.archived_at" placeholder="Choose or type a language" /><label>Signature override<textarea v-model="form.signature" rows="2" maxlength="3000" /></label></details>
      <p v-if="unresolved.length" class="at-message warning">Highlighted variables resolve when you save if the data is available. Otherwise fill or remove them: {{ unresolved.join(', ') }}</p>
      <div class="actions"><Button type="submit" :disabled="busy || !dirty">Save message</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="propose(true)">Preview latest template</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="propose(false)">Preview refreshed variables</Button></div>
    </fieldset></form>
    <div v-if="proposal" class="proposal"><h4>Review replacement</h4><p>Your existing edits will be replaced only if you apply this preview.</p><strong>{{ proposal.subject.text }}</strong><pre>{{ proposal.body.text }}</pre><div class="actions"><Button type="button" :disabled="busy" @click="apply">Apply replacement</Button><Button type="button" severity="secondary" @click="proposal = null">Keep existing message</Button></div></div>
    <div class="actions"><Button v-if="item.channel !== 'PHONE'" type="button" :disabled="busy || dirty" @click="copyResolved('subject')">Copy subject</Button><Button v-if="item.channel !== 'PHONE'" type="button" :disabled="busy || dirty" @click="copyResolved('body')">Copy message</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="copyAI">Copy AI instructions</Button><Button v-if="item.channel !== 'PHONE' && item.status !== 'SENT' && !item.archived_at" type="button" class="write-draft" :disabled="busy || dirty || !canDraft || !item.recipient_email || draftQueued || application.status === 'CLOSED'" :title="canDraft ? 'Add a draft request to the AI task list' : 'An agent must use its token with read, draft and tasks permissions in the last 15 minutes. Copy remains available.'" @click="writeToDraft">Write to draft</Button><Button v-if="item.status === 'READY'" type="button" severity="secondary" :disabled="busy" @click="change({ status: 'PREPARED' }, 'Returned to prepared.')">Return to prepared</Button></div>
    <div v-if="item.status !== 'SENT' && !item.archived_at" class="actions"><Button v-if="item.status === 'PREPARED'" type="button" :disabled="busy || dirty || unresolved.length > 0 || application.status === 'CLOSED'" @click="change({ status: 'READY' }, 'Marked ready for your manual sending.')">Mark ready</Button><Button type="button" severity="secondary" :disabled="busy || dirty" @click="change({ status: 'SENT', sent_at: new Date().toISOString() }, item.channel === 'PHONE' ? 'Call completion recorded.' : 'Actual send recorded in the tracker.')">{{ item.channel === 'PHONE' ? 'Record completed call' : 'Record already sent' }}</Button></div>
    <label v-if="copyFallback">Select and copy<textarea :value="copyFallback" rows="6" readonly @focus="($event.target as HTMLTextAreaElement).select()" /></label>
    <div v-if="!item.archived_at && item.status !== 'SENT'"><DateTimeField v-model="dueAt" label="Follow-up due (local)" :disabled="busy" /><Button type="button" :disabled="busy || !dueAt" @click="change({ due_at: new Date(dueAt).toISOString() }, 'Follow-up rescheduled.')">Reschedule</Button></div>
    <p v-if="!item.recipient_email && item.channel !== 'PHONE' && item.status !== 'SENT'" class="at-message warning">Choose or enter a recipient before requesting a mailbox draft.</p>
    <p v-if="!canDraft && item.channel !== 'PHONE'" class="draft-hint">Write to draft requires recent agent activity and read, draft and tasks permissions. You can copy the resolved message instead.</p>
    <details><summary>Reminder controls and job instructions</summary><div v-if="item.status !== 'SENT'" class="grid"><div><DateTimeField v-model="snoozeAt" label="Snooze reminder until (local)" :disabled="busy" /><div class="actions"><Button type="button" :disabled="busy || !snoozeAt" @click="change({ snoozed_until: new Date(snoozeAt).toISOString() }, 'Reminder snoozed. The due date is unchanged.')">Snooze</Button><Button type="button" severity="secondary" :disabled="busy" @click="change({ snoozed_until: null }, 'Snooze cleared.')">Clear snooze</Button></div></div><div class="actions"><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => updateApplication(application.id, { followup_paused: !application.followup_paused }), application.followup_paused ? 'Job reminders resumed.' : 'Job reminders paused.')">{{ application.followup_paused ? 'Resume job reminders' : 'Pause job reminders' }}</Button></div></div>
      <label>Instructions for this job<textarea v-model="job.instructions" rows="3" maxlength="12000" /></label><SuggestionField v-model="job.language" label="Job language override" :suggestions="languageSuggestions" :maxlength="80" :disabled="busy" /><label>Job signature override<textarea v-model="job.signature" rows="2" maxlength="3000" /></label><Button type="button" :disabled="busy" @click="perform(() => updateApplication(application.id, { followup_instructions: job.instructions, followup_customization: { language: job.language || null, tone: job.tone || null, signature: job.signature || null } }), 'Job preferences saved. Unsent messages require review again.')">Save job preferences</Button>
      <div class="actions"><Button type="button" severity="secondary" :disabled="busy" @click="change({ archived: !item.archived_at }, item.archived_at ? 'Follow-up restored.' : 'Follow-up archived.')">{{ item.archived_at ? 'Restore follow-up' : 'Archive follow-up' }}</Button><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => undoLastChange(application.id), 'Last change undone.')">Undo last change</Button></div>
    </details>
    <AIResults :application-id="application.id" :followup-id="item.id" :revision="item.revision" :disabled="busy || dirty || item.status === 'SENT' || !!item.archived_at || application.status === 'CLOSED'" @changed="emit('changed')" />
    <label>Add a note<textarea v-model="note" rows="3" placeholder="Record a reply or anything to remember." /></label><label class="reply-check"><input v-model="employerReply" type="checkbox" /> This records an employer reply (resets the unanswered follow-up count)</label><Button type="button" :disabled="busy || !note.trim()" @click="perform(async () => { await createNote(application.id, { content: note, type: 'GENERAL', employer_reply: employerReply }); note = ''; employerReply = false }, 'Note added.')">Save note</Button>
  </section>
</template>

<style scoped>
.reply-check{display:flex;gap:8px;align-items:center}.reply-check input{width:auto;margin:0}
.write-draft:disabled{background:var(--at-surface-muted);border-color:var(--at-border);color:var(--at-text-muted)}.draft-hint{font-size:13px;color:var(--at-text-muted)}.editor{padding:22px;background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;margin:18px 0}.heading{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.heading p,details p{color:var(--at-text-muted)}fieldset{padding:0;border:0;margin:0}label{display:block;font-weight:600;margin:12px 0}input,textarea{box-sizing:border-box;width:100%;font:inherit;margin-top:6px;padding:10px;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.proposal{padding:16px;border:1px solid var(--at-primary);border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}summary{cursor:pointer;font-weight:600;margin:18px 0}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:650px){.grid{grid-template-columns:1fr}.heading{flex-direction:column}.write-draft:disabled{background:var(--at-surface-muted);border-color:var(--at-border);color:var(--at-text-muted)}.draft-hint{font-size:13px;color:var(--at-text-muted)}.editor{padding:14px}}
</style>
