<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { deleteApplication, getApplication, updateApplication, type Application, type ApplicationUpdate } from './api'
import ApplicationWork from './ApplicationWork.vue'
import ApplicationInterviews from './ApplicationInterviews.vue'
import ApplicationTimeline from './ApplicationTimeline.vue'
import ApplicationDocuments from './ApplicationDocuments.vue'
import PostingReview from './PostingReview.vue'
import { contactTypes, detectJobSource, jobSourceLabel, jobSources, remotePolicies, remotePolicyLabel } from './applicationOptions'

const props = defineProps<{ id: string }>()
const application = ref<Application | null>(null)
const draft = ref<Application | null>(null)
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const saveError = ref('')
const saved = ref(false)
const clearOutcome = ref(false)
const timelineVersion = ref(0)
const contentVersion = ref(0)
const deleteConfirm = ref(false)
const outcomes = ['SUCCESSFUL', 'UNSUCCESSFUL', 'WITHDRAWN', 'JOB_CANCELLED', 'GHOSTED'] as const
const statuses = ['SUBMITTED', 'INTERVIEW', 'CLOSED'] as const
const optionalFields = [
  { key: 'location', label: 'Location' }, { key: 'contract_type', label: 'Contract type' },
] as const
const editableFields = ['job_title', 'company', 'intermediary', 'date_applied', 'job_url', 'email_reference', 'phone_number', 'contact_type', 'location', 'remote_policy', 'contract_type', 'source', 'description', 'requirements', 'status', 'outcome', 'followup_delay_days', 'max_followup_suggestions'] as const
const needsOutcomeClear = computed(() => application.value?.status === 'CLOSED' && application.value.outcome !== null && draft.value !== null && draft.value.status !== 'CLOSED')
const isKnownRemotePolicy = (value: string | null) => remotePolicies.some(option => option.value === value)
const isKnownJobSource = (value: string | null) => jobSources.some(option => option.value === value)
const hasText = (value: string | null | undefined) => Boolean(value?.trim())
const visibleOptionalFields = computed(() => optionalFields.filter(field => hasText(application.value?.[field.key])))
const visibleDescription = computed(() => (application.value?.description ?? '').replace(
  'Imported from INDEED application confirmation email. The email contains no extractable direct job posting URL. Original source and dated email evidence are preserved in the timeline. The original Indeed source is recorded; the posting URL still needs verification.', '',
).trim())

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    application.value = await getApplication(props.id)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Unable to load application'
  } finally {
    loading.value = false
  }
}

function edit() {
  draft.value = { ...application.value! }
  clearOutcome.value = false
  saveError.value = ''
  saved.value = false
}

function selectOutcome() {
  if (draft.value?.outcome) draft.value.status = 'CLOSED'
}

function onJobUrlChanged() {
  if (draft.value && application.value && draft.value.source === application.value.source) {
    draft.value.source = detectJobSource(draft.value.job_url ?? '')
  }
}

async function save() {
  if (!application.value || !draft.value || saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    const changes: ApplicationUpdate = Object.fromEntries(editableFields
      .filter(key => draft.value![key] !== application.value![key])
      .map(key => [key, draft.value![key]]))
    if (needsOutcomeClear.value && clearOutcome.value) changes.outcome = null
    application.value = await updateApplication(props.id, changes)
    draft.value = null
    saved.value = true
    timelineVersion.value++
  } catch (error) {
    saveError.value = error instanceof TypeError || (error instanceof Error && error.name === 'AbortError')
      ? 'Could not confirm the save. Your edits are still here. Cancel editing and reload the record to check its saved state.'
      : error instanceof Error ? error.message : 'Unable to save changes'
  } finally {
    saving.value = false
  }
}

async function handleUndo() {
  await load()
  contentVersion.value++
}

async function postingChanged() {
  await load()
  timelineVersion.value++
}

async function removeApplication() {
  if (!deleteConfirm.value) { deleteConfirm.value = true; return }
  saving.value = true; saveError.value = ''
  try {
    await deleteApplication(props.id)
    window.location.hash = '#/applications'
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : 'Unable to delete application.'
    deleteConfirm.value = false
  } finally { saving.value = false }
}

function onInvalidation(event: Event) {
  const changedId = (event as CustomEvent<{ application_id: string | null }>).detail.application_id
  if (changedId !== props.id) return
  void load()
  contentVersion.value++
  timelineVersion.value++
}
onMounted(() => { void load(); window.addEventListener('tracker:invalidate', onInvalidation) })
onUnmounted(() => window.removeEventListener('tracker:invalidate', onInvalidation))
</script>

<template>
  <section aria-labelledby="focus-title">
    <a v-if="!draft" class="back" href="#/applications">← All applications</a>
    <p v-if="loading" role="status">Loading application…</p>
    <div v-else-if="loadError" role="alert"><p class="error">{{ loadError }}</p><button type="button" @click="load">Try again</button></div>
    <template v-else-if="application">
      <div class="focus-heading"><div><p class="eyebrow">{{ application.company }}</p><h2 id="focus-title">{{ application.job_title }}</h2></div><div v-if="!draft" class="header-actions"><button type="button" class="primary" @click="edit">Edit application</button><button type="button" :disabled="saving" :class="{ danger: deleteConfirm }" @click="removeApplication">{{ deleteConfirm ? 'Confirm delete' : 'Delete application' }}</button></div></div>
      <p v-if="saveError && !draft" class="error" role="alert">{{ saveError }}</p>
      <p v-if="saved" class="success" role="status">Changes saved.</p>

      <form v-if="draft" class="panel" @submit.prevent="save">
        <h3>Edit application</h3>
        <fieldset :disabled="saving">
          <legend>Job details</legend>
          <div class="grid">
            <label>Job title<input v-model="draft.job_title" required maxlength="300" /></label>
            <label>Company<input v-model="draft.company" required maxlength="300" /></label>
            <label>Via / intermediary<input v-model="draft.intermediary" maxlength="300" placeholder="School, recruiter or agency" /></label>
            <label>Date applied<input v-model="draft.date_applied" type="date" required /></label>
            <label v-for="field in optionalFields" :key="field.key">{{ field.label }}<input v-model="draft[field.key]" maxlength="300" /></label>
            <label>Remote policy<select v-model="draft.remote_policy"><option :value="null">Not specified</option><option v-if="draft.remote_policy && !isKnownRemotePolicy(draft.remote_policy)" :value="draft.remote_policy">Existing: {{ draft.remote_policy }}</option><option v-for="option in remotePolicies" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label>Source<select v-model="draft.source"><option :value="null">Not specified</option><option v-if="draft.source && !isKnownJobSource(draft.source)" :value="draft.source">Existing: {{ draft.source }}</option><option v-for="option in jobSources" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          </div>
          <p class="hint">Keep at least one source: a job URL or an email reference.</p>
          <div class="grid">
            <label>Job URL<input v-model="draft.job_url" type="url" maxlength="2048" @change="onJobUrlChanged" /></label>
            <label>Email reference<input v-model="draft.email_reference" maxlength="2048" /></label>
            <label>Contact type<select v-model="draft.contact_type"><option v-for="option in contactTypes" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label>Phone number {{ draft.contact_type === 'PHONE' ? '(required for phone contact)' : '(optional)' }}<input v-model="draft.phone_number" type="tel" autocomplete="tel" placeholder="+33 6 12 34 56 78" :required="draft.contact_type === 'PHONE'" /><small>French number or +country code for other countries.</small></label>
          </div>
          <label class="long-field">Description<textarea v-model="draft.description" rows="4"></textarea></label>
          <label class="long-field">Requirements<textarea v-model="draft.requirements" rows="4"></textarea></label>
        </fieldset>

        <fieldset :disabled="saving">
          <legend>Application lifecycle</legend>
          <div class="grid">
            <label>Status<select v-model="draft.status"><option v-for="status in statuses" :key="status" :value="status">{{ status }}</option></select></label>
            <label>Outcome<select v-model="draft.outcome" :disabled="needsOutcomeClear" @change="selectOutcome"><option :value="null">No outcome</option><option v-for="outcome in outcomes" :key="outcome" :value="outcome">{{ outcome }}</option></select></label>
          </div>
          <p class="hint">Choosing an outcome closes the application. A closed application can also have no outcome.</p>
          <label v-if="needsOutcomeClear" class="checkbox"><input v-model="clearOutcome" type="checkbox" />Clear the existing {{ application.outcome }} outcome to reopen this application.</label>
        </fieldset>

        <fieldset :disabled="saving">
          <legend>Follow-up preferences</legend>
          <p class="hint">Leave blank to use the global defaults. These settings affect new follow-ups; existing due dates stay unchanged.</p>
          <div class="grid">
            <label>Follow-up delay (days)<input v-model.number="draft.followup_delay_days" type="number" min="0" max="3650" step="1" placeholder="Global default" /></label>
            <label>Maximum automatic suggestions<input v-model.number="draft.max_followup_suggestions" type="number" min="0" max="100" step="1" placeholder="Global default" /></label>
          </div>
        </fieldset>
        <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
        <div class="actions"><button class="primary" type="submit" :disabled="saving || (needsOutcomeClear && !clearOutcome)">{{ saving ? 'Saving…' : 'Save changes' }}</button><button type="button" :disabled="saving" @click="draft = null">Cancel</button></div>
      </form>

      <template v-else>
        <section class="panel" aria-label="Application overview">
          <div class="badges"><span class="badge" :class="application.status.toLowerCase()">{{ application.status }}</span><span v-if="application.outcome" class="badge" :class="application.outcome.toLowerCase()">{{ application.outcome }}</span></div>
          <dl class="details">
            <div><dt>Date applied</dt><dd>{{ application.date_applied }}</dd></div>
            <div v-if="application.intermediary"><dt>Via / intermediary</dt><dd>{{ application.intermediary }}</dd></div>
            <div><dt>Job URL</dt><dd><a v-if="application.job_url" :href="application.job_url" target="_blank" rel="noopener noreferrer">{{ application.job_url }} ↗</a><span v-else class="missing-value">Missing — use the posting search below.</span></dd></div>
            <div v-if="hasText(application.email_reference)"><dt>Email reference</dt><dd>{{ application.email_reference }}</dd></div>
            <div v-if="hasText(application.phone_number)"><dt>Phone number</dt><dd><a :href="`tel:${application.phone_number}`">{{ application.phone_number }}</a></dd></div>
            <div v-if="application.contact_type === 'PHONE'"><dt>Contact type</dt><dd>Phone</dd></div>
            <div v-if="hasText(application.remote_policy)"><dt>Remote policy</dt><dd>{{ remotePolicyLabel(application.remote_policy) }}</dd></div>
            <div v-if="hasText(application.source) && application.source !== 'OTHER'"><dt>Source</dt><dd>{{ jobSourceLabel(application.source) }}</dd></div>
            <div v-if="application.followup_delay_days !== null && application.followup_delay_days !== 7"><dt>Follow-up delay</dt><dd>{{ application.followup_delay_days }} days</dd></div>
            <div v-for="field in visibleOptionalFields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ application[field.key] }}</dd></div>
          </dl>
        </section>
        <section v-if="visibleDescription || hasText(application.requirements)" class="panel"><template v-if="visibleDescription"><h3>Description</h3><p class="text-block">{{ visibleDescription }}</p></template><template v-if="hasText(application.requirements)"><h3>Requirements</h3><p class="text-block">{{ application.requirements }}</p></template></section>
        <PostingReview :application="application" @changed="postingChanged" />
        <ApplicationDocuments :key="`documents-${contentVersion}`" :application-id="application.id" @changed="timelineVersion++" />
        <ApplicationInterviews :key="`interviews-${contentVersion}`" :application-id="application.id" @changed="timelineVersion++" />
        <ApplicationWork :key="`work-${contentVersion}`" :application-id="application.id" :phone-number="application.phone_number" @changed="timelineVersion++" />
        <ApplicationTimeline :key="timelineVersion" :application-id="application.id" @undone="handleUndo" />
      </template>
    </template>
  </section>
</template>

<style scoped>
.back { display: inline-block; margin-bottom: 28px; }
a { color: #24568b; text-underline-offset: 3px; overflow-wrap: anywhere; }
.focus-heading, .actions, .badges, .header-actions, .posting-heading { display: flex; align-items: center; gap: 12px; }
.focus-heading { justify-content: space-between; margin-bottom: 20px; }
.focus-heading > div { min-width: 0; overflow-wrap: anywhere; }
.primary { background: #263e5c; border-color: #263e5c; color: #fff; }
.primary:hover:enabled { background: #192d45; }
.danger { color: #a12c32; border-color: #a12c32; background: #fff5f5; }
.panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 24px; margin: 20px 0; }
.details { margin-top: 16px; }
.details > div { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 20px; }
.details dd { text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; }
.missing-value { color: #844d15; }
.text-block { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.6; }
.text-block:last-child { margin-bottom: 0; }
fieldset { border: 0; padding: 0; margin: 24px 0; min-width: 0; }
legend { font-weight: 650; margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
label { font-size: 14px; font-weight: 600; }
input, select, textarea { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid #b9c4d2; border-radius: 5px; font: inherit; font-weight: 400; background: #fff; color: #202c3d; }
textarea { resize: vertical; }
input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid #527ba8; outline-offset: 2px; }
.long-field { display: block; margin-top: 18px; }
.hint { font-size: 13px; color: #576678; line-height: 1.5; }
.checkbox { display: flex; align-items: flex-start; gap: 10px; line-height: 1.5; color: #844d15; }
.checkbox input { width: auto; margin-top: 3px; }
.check-now { margin-top: 12px; }
.posting-heading { justify-content: space-between; }.posting-heading button:disabled { cursor: not-allowed; }.posting-heading button.is-loading { cursor: wait; }.posting-details { margin-top:16px; }.posting-live { color:#216344 }.posting-closed { color:#a12c32 }.posting-unknown { color:#844d15 }
.success { color: #216344; font-size: 14px; }
.badge { display: inline-block; background: #eaf1fc; color: #2a5189; font-size: 12px; font-weight: 700; padding: 5px 8px; border-radius: 4px; }
.interview { background: #f0e9fa; color: #654388; } .closed, .withdrawn, .ghosted { background: #edf0f3; color: #526174; }
.successful { background: #eaf5ee; color: #216344; } .unsuccessful { background: #fcebed; color: #a12c32; } .job_cancelled { background: #fff1de; color: #844d15; }
@media (max-width: 600px) { .grid { grid-template-columns: 1fr; } .details > div { grid-template-columns: 1fr; gap: 5px; } .panel { padding: 18px; } .focus-heading { align-items: flex-start; flex-wrap: wrap; } }
</style>
