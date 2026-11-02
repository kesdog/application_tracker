<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import PageTabs from './components/shared/PageTabs.vue'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import AIResults from './components/followups/AIResults.vue'
import FollowUpLanguages from './components/followups/FollowUpLanguages.vue'
import RecipientPicker from './components/followups/RecipientPicker.vue'
import Button from 'primevue/button'
import TemplateField from './components/shared/TemplateField.vue'
import DateTimeField from './components/shared/DateTimeField.vue'
import { getFollowUpAgentStatus, getRenderedFollowUp, queueFollowUpDraft, updateFollowUp, updateApplication, getTemplateVariables, getFollowUpAIRequest, proposeFollowUp, applyFollowUpTemplate, createNote, undoLastChange, type FollowUp, type Application, type FollowUpChanges, type TemplateVariable, type MessageProposal } from './api'
const props = defineProps<{ item: FollowUp; application: Application }>()
const emit = defineEmits<{ changed: [] }>()
const editorTab = ref('message')
const variables = ref<TemplateVariable[]>([])
const form = reactive({ subject: '', body: '', instructions: '', language: '', tone: '', signature: '' })
const job = reactive({ instructions: '', language: '', tone: '', signature: '' })
let savedJobForm = ''
const jobRevision = ref(1)
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
async function refreshAgent() {
  try { const status = await getFollowUpAgentStatus(); if (!disposed) canDraft.value = status.can_draft }
  catch { if (!disposed) canDraft.value = false }
}
function writeToDraft() {
  return perform(async () => { await queueFollowUpDraft(props.application.id, props.item.id, props.item.revision); queuedFollowupId = props.item.id; draftQueued.value = true }, t("Added to the AI task list. The agent can write it to a draft."), false)
}
async function copyResolved(field: 'subject' | 'body') {
  error.value = ''
  try {
    if (props.item.content_available === false) throw new Error(t("Message content is not synchronized. Prepare and review a message on this device first."))
    const rendered = await getRenderedFollowUp(props.application.id, props.item.id)
    if (rendered.revision !== props.item.revision) throw new Error(t("The message changed. Reload it before copying."))
    const text = rendered[field]
    if (text.missing.length || text.unknown.length) throw new Error(t("Fill or remove these variables before copying: {p0}", { p0: [...text.missing, ...text.unknown].join(', ') }))
    await copy(text.text, field === 'subject' ? t("Subject") : t("Message"), true)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to resolve message variables.") }
}
const dirty = computed(() => form.subject !== props.item.subject || form.body !== props.item.body || form.instructions !== props.item.instructions || form.language !== (props.item.customization.language ?? '') || form.tone !== (props.item.customization.tone ?? '') || form.signature !== (props.item.customization.signature ?? ''))
const unresolved = computed(() => [...new Set([...(form.subject + '\n' + form.body).matchAll(/\{([^{}\n]+)\}/g)].map(m => m[1]))])
function localTime(value: string | null) { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
function reset() {
  if (props.item.id !== queuedFollowupId) draftQueued.value = false
  const preserveJobEdits = savedJobForm !== '' && JSON.stringify(job) !== savedJobForm
  Object.assign(form, { subject: props.item.subject, body: props.item.body, instructions: props.item.instructions, language: props.item.customization.language ?? '', tone: props.item.customization.tone ?? '', signature: props.item.customization.signature ?? '' })
  const jobDefaults = { instructions: props.application.followup_instructions ?? '', language: props.application.followup_customization?.language ?? '', tone: props.application.followup_customization?.tone ?? '', signature: props.application.followup_customization?.signature ?? '' }
  if (!preserveJobEdits) { Object.assign(job, jobDefaults); jobRevision.value = props.application.revision }
  savedJobForm = JSON.stringify(jobDefaults)
  dueAt.value = localTime(props.item.due_at); snoozeAt.value = localTime(props.item.snoozed_until); proposal.value = null
}
watch(() => props.item, reset, { immediate: true })
async function perform(action: () => Promise<unknown>, message: string, saveEdits = false) {
  if (busy.value) return
  if (dirty.value && !saveEdits) { error.value = t("Save your message edits before changing another setting."); return }
  busy.value = true; error.value = ''; notice.value = ''
  try { await action(); notice.value = message; emit('changed') }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to save. Your entries are retained.") }
  finally { busy.value = false }
}
function save() { return perform(() => updateFollowUp(props.application.id, props.item.id, { subject: form.subject, body: form.body, instructions: form.instructions, customization: { language: form.language || null, tone: form.tone || null, signature: form.signature || null }, expected_revision: props.item.revision }), t("Message saved. It has not been sent."), true) }
function change(data: FollowUpChanges, message: string) { return perform(() => updateFollowUp(props.application.id, props.item.id, { ...data, expected_revision: props.item.revision }), message) }
async function copy(text: string, label: string, allowTags = false) {
  error.value = ''; copyFallback.value = ''
  if (!allowTags && /\{[^{}\n]+\}/.test(text)) { error.value = t("Fill or remove the highlighted variables and save before copying."); return }
  try { await navigator.clipboard.writeText(text); notice.value = t("{p0} copied. Nothing was sent.", { p0: label }) }
  catch { copyFallback.value = text; notice.value = t("Clipboard access is unavailable. Select and copy the text below.") }
}
async function copyAI() {
  try { await copy(JSON.stringify(await getFollowUpAIRequest(props.application.id, props.item.id), null, 2), t("AI instructions"), true) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to prepare AI instructions.") }
}
async function propose(latest: boolean) {
  error.value = ''; proposalLatest.value = latest
  try { proposal.value = await proposeFollowUp(props.application.id, props.item.id, latest) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to prepare replacement.") }
}
function apply() {
  if (!proposal.value) return
  return perform(() => applyFollowUpTemplate(props.application.id, props.item.id, proposal.value!.expected_revision, proposalLatest.value), t("Replacement applied. Review the message before requesting a draft."))
}
onMounted(async () => { void refreshAgent(); statusTimer = setInterval(refreshAgent, 60000); window.addEventListener('focus', refreshAgent); try { variables.value = await getTemplateVariables() } catch { error.value = t("Unable to load template variables.") } })
onUnmounted(() => { disposed = true; clearInterval(statusTimer); window.removeEventListener('focus', refreshAgent) })
</script>

<template>
  <section class="editor" :aria-busy="busy"><div class="heading"><div><h3>{{ application.company }} · {{ application.job_title }}</h3><p>{{ t("Follow-up #") }}{{ item.sequence_number }} · {{ messageText(String((item.status === 'SENT' && item.channel === 'PHONE' ? t("Completed") : item.status.toLowerCase()) ?? '')) }}<span v-if="item.archived_at"> {{ t("· archived") }}</span><span v-if="application.followup_paused"> {{ t("· reminders paused") }}</span></p></div><a :href="`#/applications/${application.id}`">{{ t("Application") }}</a></div>
    <p v-if="item.content_available === false" class="at-message warning" role="status">{{ t("Only this follow-up's schedule and state were synchronized. Message content stays on its original device. Prepare and review a local message before copying, approving or requesting a draft.") }}</p>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p><p v-if="notice" class="at-message success" role="status">{{ messageText(String((notice) ?? '')) }}</p>
    <p v-if="item.channel === 'PHONE'">{{ t("Phone follow-up ·") }} {{ application.phone_number }}{{ t(". Record completion after making the call.") }}</p>
    <PageTabs v-model="editorTab" :label="t('Follow-up editor')" :tabs="[{ value: 'message', get label() { return t('Message') }, icon: 'pi-envelope' }, { value: 'recipients', get label() { return t('Recipient') }, icon: 'pi-user' }, { value: 'schedule', get label() { return t('Schedule') }, icon: 'pi-calendar' }, { value: 'ai', get label() { return t('AI assistance') }, icon: 'pi-sparkles' }, { value: 'notes', get label() { return t('Notes') }, icon: 'pi-file-edit' }]">
    <template #message>
      <FollowUpLanguages :application="application" :item="item" :disabled="busy || dirty" @changed="emit('changed')" />
      <div v-if="item.channel !== 'PHONE'" class="recipient-summary"><span>{{ item.recipient_email ? t("To: {p0}", { p0: item.recipient_email }) : t("No recipient selected") }}</span><Button type="button" severity="secondary" text @click="editorTab = 'recipients'">{{ item.recipient_email ? t("Change recipient") : t("Choose recipient") }}</Button></div>
    <form v-if="item.channel !== 'PHONE'" @submit.prevent="save"><fieldset :disabled="busy || item.status === 'SENT' || !!item.archived_at"><legend class="sr-only">{{ t("Prepared follow-up") }}</legend>
      <TemplateField v-model="form.subject" :label="t('Follow-up subject')" :variables="variables" :rows="2" :disabled="busy || item.status === 'SENT' || !!item.archived_at" />
      <TemplateField v-model="form.body" :label="t('Follow-up message')" :variables="variables" :rows="10" :disabled="busy || item.status === 'SENT' || !!item.archived_at" />

      <details><summary>{{ t("Customize this message") }}</summary>      <label>{{ t("Instructions for this follow-up") }}<textarea v-model="form.instructions" rows="3" maxlength="12000" /></label><p>{{ t("Blank values inherit job preferences and the saved default template preferences.") }}</p><label>{{ t("Signature override") }}<textarea v-model="form.signature" rows="2" maxlength="3000" /></label></details>
      <p v-if="unresolved.length" class="at-message warning">{{ t("Highlighted variables resolve when you save if the data is available. Otherwise fill or remove them:") }} {{ unresolved.join(', ') }}</p>
      <div class="actions"><Button type="submit" :disabled="busy || !dirty">{{ t("Save message") }}</Button></div><details><summary>{{ t("Refresh from a template") }}</summary><div class="actions"><Button type="button" severity="secondary" :disabled="busy || dirty || item.content_available === false" @click="propose(true)">{{ t("Preview latest template") }}</Button><Button type="button" severity="secondary" :disabled="busy || dirty || item.content_available === false" @click="propose(false)">{{ t("Preview refreshed variables") }}</Button></div></details>
    </fieldset></form>
    <div v-if="proposal" class="proposal"><h4>{{ t("Review replacement") }}</h4><p>{{ t("Your existing edits will be replaced only if you apply this preview.") }}</p><strong>{{ proposal.subject.text }}</strong><pre>{{ proposal.body.text }}</pre><div class="actions"><Button type="button" :disabled="busy" @click="apply">{{ t("Apply replacement") }}</Button><Button type="button" severity="secondary" @click="proposal = null">{{ t("Keep existing message") }}</Button></div></div>
    <div class="actions"><Button v-if="item.channel !== 'PHONE'" type="button" :disabled="busy || dirty || item.content_available === false" @click="copyResolved('subject')">{{ t("Copy subject") }}</Button><Button v-if="item.channel !== 'PHONE'" type="button" :disabled="busy || dirty || item.content_available === false" @click="copyResolved('body')">{{ t("Copy message") }}</Button><Button v-if="item.channel !== 'PHONE' && item.status !== 'SENT' && !item.archived_at" type="button" class="write-draft" :disabled="busy || dirty || item.content_available === false || !canDraft || !item.recipient_email || draftQueued || application.status === 'CLOSED'" :title="messageText(String((canDraft ? t('Add a draft request to the AI task list') : t('An agent must use its token with read, draft and tasks permissions in the last 15 minutes. Copy remains available.')) ?? ''))" @click="writeToDraft">{{ t("Write to draft") }}</Button><Button v-if="item.status === 'READY'" type="button" severity="secondary" :disabled="busy" @click="change({ status: 'PREPARED' }, t('Returned to prepared.'))">{{ t("Return to prepared") }}</Button></div>
    <details v-if="item.status !== 'SENT' && !item.archived_at"><summary>{{ t("Manual sending & completion") }}</summary><div class="actions"><Button v-if="item.status === 'PREPARED'" type="button" :disabled="busy || dirty || item.content_available === false || unresolved.length > 0 || application.status === 'CLOSED'" @click="change({ status: 'READY' }, t('Marked ready for your manual sending.'))">{{ t("Mark ready") }}</Button><Button type="button" severity="secondary" :disabled="busy || dirty || item.content_available === false" @click="change({ status: 'SENT', sent_at: new Date().toISOString() }, item.channel === 'PHONE' ? t('Call completion recorded.') : t('Actual send recorded in the tracker.'))">{{ item.channel === 'PHONE' ? t("Record completed call") : t("Record already sent") }}</Button></div></details>
    <label v-if="copyFallback">{{ t("Select and copy") }}<textarea :value="copyFallback" rows="6" readonly @focus="($event.target as HTMLTextAreaElement).select()" /></label>

    <p v-if="!canDraft && item.channel !== 'PHONE'" class="draft-hint">{{ t("No active agent for drafting. Copy is available.") }}</p>
    </template><template #recipients>    <RecipientPicker v-if="item.channel !== 'PHONE' && item.status !== 'SENT' && !item.archived_at" :application-id="application.id" :followup="item" :disabled="busy || dirty || item.content_available === false" :closed="application.status === 'CLOSED'" @changed="emit('changed')" /><p v-if="item.status === 'SENT' || item.archived_at">{{ item.recipient_email ? t("Recorded recipient: {p0}", { p0: item.recipient_email }) : t("No recipient recorded.") }}</p></template>
    <template #schedule>    <div v-if="!item.archived_at && item.status !== 'SENT'"><DateTimeField v-model="dueAt" :label="t('Follow-up due (local)')" :disabled="busy" /><Button type="button" :disabled="busy || !dueAt" @click="change({ due_at: new Date(dueAt).toISOString() }, t('Follow-up rescheduled.'))">{{ t("Reschedule") }}</Button></div>
    <p v-if="item.status !== 'SENT' && !item.archived_at && !application.followup_paused && application.status !== 'CLOSED'"><a :href="`/api/applications/${application.id}/followups/${item.id}/calendar.ics`" download>{{ t("Download calendar reminder") }}</a> {{ t("· Import it into your calendar as an optional reminder. Re-export after changing its date.") }}</p>
    <div class="schedule-controls"><div v-if="item.status !== 'SENT'" class="grid"><div><DateTimeField v-model="snoozeAt" :label="t('Snooze reminder until (local)')" :disabled="busy" /><div class="actions"><Button type="button" :disabled="busy || !snoozeAt" @click="change({ snoozed_until: new Date(snoozeAt).toISOString() }, t('Reminder snoozed. The due date is unchanged.'))">{{ t("Snooze") }}</Button><Button type="button" severity="secondary" :disabled="busy" @click="change({ snoozed_until: null }, t('Snooze cleared.'))">{{ t("Clear snooze") }}</Button></div></div><div class="actions"><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => updateApplication(application.id, { followup_paused: !application.followup_paused, expected_revision: application.revision }), application.followup_paused ? t('Job reminders resumed.') : t('Job reminders paused.'))">{{ application.followup_paused ? t("Resume job reminders") : t("Pause job reminders") }}</Button></div></div>
      <label>{{ t("Instructions for this job") }}<textarea v-model="job.instructions" rows="3" maxlength="12000" /></label><label>{{ t("Job signature override") }}<textarea v-model="job.signature" rows="2" maxlength="3000" /></label><Button type="button" :disabled="busy" @click="perform(() => updateApplication(application.id, { expected_revision: jobRevision, followup_instructions: job.instructions, followup_customization: { language: job.language || null, tone: job.tone || null, signature: job.signature || null } }), t('Job preferences saved. Unsent messages require review again.'))">{{ t("Save job preferences") }}</Button>
      <div class="actions"><Button type="button" severity="secondary" :disabled="busy" @click="change({ archived: !item.archived_at }, item.archived_at ? t('Follow-up restored.') : t('Follow-up archived.'))">{{ item.archived_at ? t("Restore follow-up") : t("Archive follow-up") }}</Button><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => undoLastChange(application.id), t('Last change undone.'))">{{ t("Undo last change") }}</Button></div>
    </div>
</template>
    <template #ai><Button type="button" severity="secondary" :disabled="busy || dirty || item.content_available === false" @click="copyAI">{{ t("Copy AI instructions") }}</Button>    <AIResults :application-id="application.id" :followup-id="item.id" :revision="item.revision" :disabled="busy || dirty || item.status === 'SENT' || !!item.archived_at || application.status === 'CLOSED'" @changed="emit('changed')" />
</template>
    <template #notes>    <label>{{ t("Add a note") }}<textarea v-model="note" rows="3" :placeholder="t('Record a reply or anything to remember.')" /></label><label class="reply-check"><input v-model="employerReply" type="checkbox" /> {{ t("This records an employer reply (resets the unanswered follow-up count)") }}</label><Button type="button" :disabled="busy || !note.trim()" @click="perform(async () => { await createNote(application.id, { content: note, type: 'GENERAL', employer_reply: employerReply }); note = ''; employerReply = false }, t('Note added.'))">{{ t("Save note") }}</Button></template></PageTabs>
  </section>
</template>

<style scoped>
.recipient-summary{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:14px;border-bottom:1px solid var(--at-border);padding-bottom:10px;margin-bottom:14px}.reply-check{display:flex;gap:8px;align-items:center}.reply-check input{width:auto;margin:0}
.write-draft:disabled{background:var(--at-surface-muted);border-color:var(--at-border);color:var(--at-text-muted)}.draft-hint{font-size:13px;color:var(--at-text-muted)}.editor{padding:22px;background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;margin:18px 0}.heading{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.heading p,details p{color:var(--at-text-muted)}fieldset{padding:0;border:0;margin:0}label{display:block;font-weight:600;margin:12px 0}input,textarea{box-sizing:border-box;width:100%;font:inherit;margin-top:6px;padding:10px;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.proposal{padding:16px;border:1px solid var(--at-primary);border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}summary{cursor:pointer;font-weight:600;margin:18px 0}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:650px){.grid{grid-template-columns:1fr}.heading{flex-direction:column}.write-draft:disabled{background:var(--at-surface-muted);border-color:var(--at-border);color:var(--at-text-muted)}.draft-hint{font-size:13px;color:var(--at-text-muted)}.editor{padding:14px}}
</style>
