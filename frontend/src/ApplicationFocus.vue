<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import PageTabs from './components/shared/PageTabs.vue'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import DatePicker from './DatePicker.vue'
import NumberField from './components/shared/NumberField.vue'
import InputText from 'primevue/inputtext'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { deleteApplication, getApplication, getDashboard, updateApplication, type Application, type ApplicationUpdate, type DashboardData } from './api'
import { useConfirm } from 'primevue/useconfirm'
import CompletedFollowUps from './components/applications/CompletedFollowUps.vue'
import ApplicationStatusTag from './components/applications/ApplicationStatusTag.vue'
import ApplicationOutcomeTag from './components/applications/ApplicationOutcomeTag.vue'
import ApplicationNextAction from './components/applications/ApplicationNextAction.vue'
import AppTag from './components/shared/AppTag.vue'
import { postingStatusMeta, remotePolicyMeta, statusOptions, outcomeOptions } from './presentation/applicationPresentation'
import { nextApplicationAction } from './presentation/nextAction'
import ApplicationWork from './ApplicationWork.vue'
import BusyIndicator from './components/shared/BusyIndicator.vue'
import ApplicationInterviews from './ApplicationInterviews.vue'
import ApplicationTimeline from './ApplicationTimeline.vue'
import ApplicationDocuments from './ApplicationDocuments.vue'
import PostingReview from './PostingReview.vue'
import EmailReference from './EmailReference.vue'
import { contactTypes, detectJobSource, jobSourceLabel, jobSources, remotePolicies, remotePolicyLabel } from './applicationOptions'

const props = defineProps<{ id: string }>()
const application = ref<Application | null>(null)
const draft = ref<Application | null>(null)
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const saveError = ref('')
const saved = ref(false)
const postingCopyNotice = ref('')
const postingCopyError = ref(false)
const clearOutcome = ref(false)
const timelineVersion = ref(0)
const contentVersion = ref(0)
const confirm = useConfirm()
const dashboard = ref<DashboardData | null>(null)
const nextAction = computed(() => nextApplicationAction(props.id, dashboard.value))
const optionalFields = [
  { key: 'location', get label() { return t("Location") } }, { key: 'contract_type', get label() { return t("Contract type") } },
] as const
const editableFields = ['job_title', 'company', 'intermediary', 'date_applied', 'job_url', 'email_reference', 'phone_number', 'contact_email', 'contact_name', 'deadline', 'deadline_kind', 'contact_type', 'location', 'remote_policy', 'contract_type', 'source', 'description', 'requirements', 'status', 'outcome', 'followup_delay_days', 'max_followup_suggestions'] as const
const needsOutcomeClear = computed(() => application.value?.status === 'CLOSED' && application.value.outcome !== null && draft.value !== null && draft.value.status !== 'CLOSED')
const isKnownRemotePolicy = (value: string | null) => remotePolicies.some(option => option.value === value)
const isKnownJobSource = (value: string | null) => jobSources.some(option => option.value === value)
const hasText = (value: string | null | undefined) => Boolean(value?.trim())
const visibleOptionalFields = computed(() => optionalFields.filter(field => hasText(application.value?.[field.key])))
const visibleDescription = computed(() => (application.value?.description ?? '').replace(
  t("Imported from INDEED application confirmation email. The email contains no extractable direct job posting URL. Original source and dated email evidence are preserved in the timeline. The original Indeed source is recorded; the posting URL still needs verification."), '',
).trim())

async function copyJobPosting() {
  if (!application.value?.job_url) return
  try {
    await navigator.clipboard.writeText(application.value.job_url)
    postingCopyError.value = false
    postingCopyNotice.value = t("Job posting link copied.")
  } catch {
    postingCopyError.value = true
    postingCopyNotice.value = t("Could not copy the link. Right-click Job posting to copy its address.")
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [record, summary] = await Promise.all([getApplication(props.id), getDashboard().catch(() => null)])
    application.value = record
    dashboard.value = summary
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : t("Unable to load application")
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
    if (!draft.value.deadline) {
      draft.value.deadline = null
      draft.value.deadline_kind = null
    }
    const changes: ApplicationUpdate = Object.fromEntries(editableFields
      .filter(key => draft.value![key] !== application.value![key])
      .map(key => [key, draft.value![key]]))
    if (needsOutcomeClear.value && clearOutcome.value) changes.outcome = null
    application.value = await updateApplication(props.id, { ...changes, expected_revision: draft.value.revision })
    draft.value = null
    saved.value = true
    timelineVersion.value++
  } catch (error) {
    saveError.value = error instanceof TypeError || (error instanceof Error && error.name === 'AbortError')
      ? t("Could not confirm the save. Your edits are still here. Cancel editing and reload the record to check its saved state.")
      : error instanceof Error ? error.message : t("Unable to save changes")
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
  saving.value = true; saveError.value = ''
  try {
    await deleteApplication(props.id)
    window.location.hash = '#/applications'
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : t("Unable to delete application.")
  } finally { saving.value = false }
}

function confirmDelete() {
  confirm.require({ get header() { return t("Delete application?") }, message: t("Delete {p0} at {p1}? This action cannot be undone.", { p0: application.value?.job_title, p1: application.value?.company }), icon: 'pi pi-exclamation-triangle', rejectProps: { get label() { return t("Keep application") }, severity: 'secondary', outlined: true }, acceptProps: { get label() { return t("Delete application") }, severity: 'danger' }, defaultFocus: 'reject', accept: () => { void removeApplication() } })
}
async function workChanged() {
  timelineVersion.value++
  dashboard.value = await getDashboard().catch(() => null)
}

function onInvalidation(event: Event) {
  if ((event as CustomEvent).detail.topic === 'recipient.updated') return
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
    <a v-if="!draft" class="back" href="#/applications">{{ t("← All applications") }}</a>
    <BusyIndicator v-if="loading" :label="t('Loading application…')" />
    <div v-else-if="loadError" role="alert"><p class="at-message error">{{ errorText(loadError) }}</p><Button type="button" @click="load">{{ t("Try again") }}</Button></div>
    <template v-else-if="application">
      <div class="focus-heading"><div><p class="eyebrow">{{ application.company }}<template v-if="application.location"> · {{ application.location }}</template><template v-if="application.remote_policy"> · {{ messageText(String((remotePolicyMeta[application.remote_policy]?.label ?? application.remote_policy) ?? '')) }}</template></p><h2 id="focus-title">{{ application.job_title }}</h2><div class="badges"><ApplicationStatusTag :status="application.status" /><CompletedFollowUps :count="application.completed_followup_count" /><ApplicationOutcomeTag v-if="application.outcome" :outcome="application.outcome" /></div></div><div v-if="!draft" class="header-actions"><Button type="button" @click="edit">{{ t("Edit application") }}</Button><Button type="button" severity="danger" outlined :disabled="saving" @click="confirmDelete">{{ t("Delete application") }}</Button></div></div>
      <div v-if="!draft && nextAction" class="focus-next"><span>{{ t("Next step") }}</span><ApplicationNextAction :action="nextAction" /></div>
      <p v-if="saveError && !draft" class="at-message error" role="alert">{{ errorText(saveError) }}</p>
      <p v-if="saved" class="at-message success" role="status">{{ t("Changes saved.") }}</p>

      <form v-if="draft" class="panel" @submit.prevent="save">
        <h3>{{ t("Edit application") }}</h3>
        <fieldset :disabled="saving">
          <legend>{{ t("Job details") }}</legend>
          <div class="grid">
            <label>{{ t("Job title") }}<InputText class="at-form-control" v-model="draft.job_title" required maxlength="300" /></label>
            <label>{{ t("Company") }}<InputText class="at-form-control" v-model="draft.company" required maxlength="300" /></label>
            <DatePicker v-model="draft.date_applied" :label="t('Date applied')" :disabled="saving" required />
          </div>
          <details><summary>{{ t("More role details") }}</summary><div class="grid">
            <label>{{ t("Via / intermediary") }}<InputText class="at-form-control" v-model="draft.intermediary" maxlength="300" :placeholder="t('School, recruiter or agency')" /></label>

            <label v-for="field in optionalFields" :key="field.key">{{ messageText(String((field.label) ?? '')) }}<InputText class="at-form-control" v-model="draft[field.key]" maxlength="300" /></label>
            <div><label id="focus-remote-label">{{ t("Remote policy") }}</label><SelectButton class="at-form-control" v-model="draft.remote_policy" :options="remotePolicies" option-label="label" option-value="value" aria-labelledby="focus-remote-label" :disabled="saving" /><small v-if="draft.remote_policy && !isKnownRemotePolicy(draft.remote_policy)">{{ t("Existing:") }} {{ draft.remote_policy }}{{ t(". Select an option to replace it.") }}</small></div>
            <label>{{ t("Source") }}<Select class="at-form-control" :aria-label="t('Source')" v-model="draft.source" :disabled="saving" :options="[{ value: null, get label() { return t('Not specified') } }, ...(draft.source && !isKnownJobSource(draft.source) ? [{ value: draft.source, label: t('Existing: ') + draft.source }] : []), ...jobSources]" option-label="label" option-value="value" option-disabled="disabled" /></label>
          </div>
          </details>
          <p class="hint">{{ t("Keep at least one source: a job URL or an email reference.") }}</p>
          <div class="grid">
            <label>{{ t("Job URL") }}<InputText class="at-form-control" v-model="draft.job_url" type="url" maxlength="2048" @change="onJobUrlChanged" /></label>
            <label>{{ t("Email references") }}<Textarea class="at-form-control" v-model="draft.email_reference" maxlength="2048" rows="3" /><small>{{ t("One message link, ID, or subject per line.") }}</small></label>
          </div><details><summary>{{ t("Contact, deadline & role notes") }}</summary><div class="grid">
            <label>{{ t("Contact type") }}<Select class="at-form-control" :aria-label="t('Contact type')" v-model="draft.contact_type" :disabled="saving" :options="contactTypes" option-label="label" option-value="value" option-disabled="disabled" /></label>
            <label>{{ t("Contact name") }}<InputText class="at-form-control" v-model="draft.contact_name" maxlength="300" /></label>
            <label>{{ t("Contact email") }}<InputText class="at-form-control" v-model="draft.contact_email" type="email" maxlength="320" :placeholder="t('name@company.com')" /></label>
            <label>{{ t("Phone number") }} {{ draft.contact_type === 'PHONE' ? t("(required for phone contact)") : '(optional)' }}<InputText class="at-form-control" v-model="draft.phone_number" type="tel" autocomplete="tel" placeholder="+33 6 12 34 56 78" :required="draft.contact_type === 'PHONE'" /><small>{{ t("French number or +country code for other countries.") }}</small></label>
            <DatePicker v-model="draft.deadline" :label="t('Posting deadline (optional)')" :disabled="saving" @update:model-value="!$event && (draft.deadline_kind = null)" />
            <div v-if="draft.deadline"><label for="focus-deadline-kind">{{ t("Deadline type") }}</label><Select input-id="focus-deadline-kind" v-model="draft.deadline_kind" :options="[{ value: 'APPLICATION_CLOSING', get label() { return t('Applications close') } }, { value: 'FIRST_ROUND', get label() { return t('First-round selection') } }]" option-label="label" option-value="value" :disabled="saving" class="at-form-control" /></div>
          </div>
          <label class="long-field">{{ t("Description") }}<Textarea class="at-form-control" v-model="draft.description" rows="4"></Textarea></label>
          <label class="long-field">{{ t("Requirements") }}<Textarea class="at-form-control" v-model="draft.requirements" rows="4"></Textarea></label>
          </details>
        </fieldset>

        <fieldset :disabled="saving">
          <legend>{{ t("Application lifecycle") }}</legend>
          <div class="grid">
            <label>{{ t("Status") }}<Select class="at-form-control" :aria-label="t('Status')" v-model="draft.status" :disabled="saving" :options="statusOptions" option-label="label" option-value="value" option-disabled="disabled" /></label>
            <label>{{ t("Outcome") }}<Select class="at-form-control" :aria-label="t('Outcome')" v-model="draft.outcome" :disabled="saving || (needsOutcomeClear)" @change="selectOutcome" :options="[{ value: null, get label() { return t('No outcome') } }, ...outcomeOptions]" option-label="label" option-value="value" option-disabled="disabled" /></label>
          </div>
          <p class="hint">{{ t("Choosing an outcome closes the application. A closed application can also have no outcome.") }}</p>
          <label v-if="needsOutcomeClear" class="checkbox"><input v-model="clearOutcome" type="checkbox" />{{ t("Clear the existing") }} {{ application.outcome }} {{ t("outcome to reopen this application.") }}</label>
        </fieldset>

        <details><summary>{{ t("Follow-up preferences") }}</summary><fieldset :disabled="saving">
          <legend class="sr-only">{{ t("Follow-up preferences") }}</legend>
          <p class="hint">{{ t("Leave blank to use the global defaults. These settings affect new follow-ups; existing due dates stay unchanged.") }}</p>
          <div class="grid">
            <NumberField v-model="draft.followup_delay_days" :label="t('Follow-up delay (days)')" :disabled="saving" :min="0" :max="3650" :placeholder="t('Global default')" />
            <NumberField v-model="draft.max_followup_suggestions" :label="t('Maximum automatic suggestions')" :disabled="saving" :min="0" :max="100" :placeholder="t('Global default')" />
          </div>
        </fieldset>
        </details>
        <p v-if="saveError" class="at-message error" role="alert">{{ errorText(saveError) }}</p>
        <div class="actions"><Button class="primary" type="submit" :disabled="saving || (needsOutcomeClear && !clearOutcome)">{{ saving ? t("Saving…") : t("Save changes") }}</Button><Button type="button" :disabled="saving" @click="draft = null">{{ t("Cancel") }}</Button></div>
      </form>

      <PageTabs v-else :label="t('Application sections')" :tabs="[
        { value: 'overview', get label() { return t('Overview') }, icon: 'pi-briefcase' }, { value: 'followups', get label() { return t('Follow-ups') }, icon: 'pi-envelope' }, { value: 'notes', get label() { return t('Notes') }, icon: 'pi-file-edit' }, { value: 'tasks', get label() { return t('Tasks') }, icon: 'pi-check-square' },
        { value: 'interviews', get label() { return t('Interviews') }, icon: 'pi-calendar' }, { value: 'documents', get label() { return t('Documents') }, icon: 'pi-file' },
        { value: 'timeline', get label() { return t('Timeline') }, icon: 'pi-history' },
      ]">
      <template #overview>
        <section class="panel" :aria-label="t('Application overview')">
          <div class="overview-top"><div class="source-actions"><a v-if="application.job_url" :href="application.job_url" target="_blank" rel="noopener noreferrer">{{ t("Job posting") }} <i class="pi pi-external-link" aria-hidden="true" /></a><span v-else class="missing-value">{{ t("Job posting not linked") }}</span><Button v-if="application.job_url" type="button" severity="secondary" outlined size="small" @click="copyJobPosting"><i class="pi pi-copy" aria-hidden="true" />{{ t("Copy job posting") }}</Button></div><AppTag v-bind="postingStatusMeta[application.posting_status]" /></div>
          <p v-if="postingCopyNotice" :role="postingCopyError ? 'alert' : 'status'" class="hint">{{ postingCopyNotice }}</p>
          <div class="overview-meta"><span>{{ t("Applied") }} {{ application.date_applied }}</span><span v-if="application.deadline">{{ application.deadline_kind === 'FIRST_ROUND' ? t("First-round selection") : t("Applications close") }} {{ application.deadline }}</span><EmailReference v-if="hasText(application.email_reference)" :reference="application.email_reference" :context="t('{p0} at {p1}', { p0: application.job_title, p1: application.company })" /></div>
          <details class="supporting-details"><summary>{{ t("Application details") }}</summary><dl class="details">
            <div v-if="hasText(application.contact_name)"><dt>{{ t("Contact") }}</dt><dd>{{ application.contact_name }}</dd></div>
            <div v-if="hasText(application.contact_email)"><dt>{{ t("Contact email") }}</dt><dd><a :href="`mailto:${application.contact_email}`">{{ application.contact_email }}</a></dd></div>
            <div v-if="application.intermediary"><dt>{{ t("Via / intermediary") }}</dt><dd>{{ application.intermediary }}</dd></div>
            <div v-if="hasText(application.phone_number)"><dt>{{ t("Phone number") }}</dt><dd><a :href="`tel:${application.phone_number}`">{{ application.phone_number }}</a></dd></div>
            <div v-if="application.contact_type === 'PHONE'"><dt>{{ t("Contact type") }}</dt><dd>{{ t("Phone") }}</dd></div>
            <div v-if="hasText(application.remote_policy)"><dt>{{ t("Remote policy") }}</dt><dd>{{ remotePolicyLabel(application.remote_policy) }}</dd></div>
            <div v-if="hasText(application.source) && application.source !== 'OTHER'"><dt>{{ t("Source") }}</dt><dd>{{ jobSourceLabel(application.source) }}</dd></div>
            <div v-if="application.followup_delay_days !== null && application.followup_delay_days !== 7"><dt>{{ t("Follow-up delay") }}</dt><dd>{{ application.followup_delay_days }} {{ t("days") }}</dd></div>
            <div v-for="field in visibleOptionalFields" :key="field.key"><dt>{{ messageText(String((field.label) ?? '')) }}</dt><dd>{{ application[field.key] }}</dd></div>
          </dl></details>
        </section>
        <details v-if="visibleDescription || hasText(application.requirements)" class="panel"><summary>{{ t("Role description & requirements") }}</summary><template v-if="visibleDescription"><h3>{{ t("Description") }}</h3><p class="text-block">{{ visibleDescription }}</p></template><template v-if="hasText(application.requirements)"><h3>{{ t("Requirements") }}</h3><p class="text-block">{{ application.requirements }}</p></template></details>
        <details class="posting-tools"><summary>{{ t("Posting checks & search") }}</summary><PostingReview :application="application" embedded @changed="postingChanged" /></details>
      </template>
      <template v-for="view in (['followups', 'notes', 'tasks'] as const)" :key="view" #[view]><ApplicationWork :key="`${view}-${contentVersion}`" :application-id="application.id" :phone-number="application.phone_number" :view="view" :closed="application.status === 'CLOSED'" @changed="workChanged" /></template>
      <template #interviews>        <ApplicationInterviews :key="`interviews-${contentVersion}`" :application-id="application.id" @changed="workChanged" /></template>
      <template #documents>        <ApplicationDocuments :key="`documents-${contentVersion}`" :application-id="application.id" @changed="timelineVersion++" /></template>
      <template #timeline><ApplicationTimeline :key="timelineVersion" :application-id="application.id" embedded @undone="handleUndo" /></template>
      </PageTabs>
    </template>
  </section>
</template>

<style scoped>
@layer legacy {
.back { display: inline-block; margin-bottom: 28px; }
a { color: var(--at-link); text-underline-offset: 3px; overflow-wrap: anywhere; }
.focus-heading, .actions, .badges, .header-actions, .posting-heading { display: flex; align-items: center; gap: 12px; }
.focus-heading { justify-content: space-between; margin-bottom: 20px; }
.focus-heading .badges { margin-top:12px; }.header-actions { flex-wrap:wrap; }
.focus-next { display:flex; align-items:center; gap:16px; padding:16px; border:1px solid var(--at-border); border-radius:8px; background:var(--at-surface); }.focus-next > span { font-size:12px; color:var(--at-text-muted); }
.focus-heading > div { min-width: 0; overflow-wrap: anywhere; }
.primary { background: var(--at-primary); border-color: var(--at-primary); color:var(--at-primary-contrast); }
.primary:hover:enabled { background: var(--at-primary-hover); }
.danger { color: var(--at-unsuccessful); border-color: var(--at-unsuccessful); background: color-mix(in srgb, var(--at-unsuccessful) 10%, var(--at-surface)); }
.panel { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; padding: 24px; margin: 20px 0; }
.details { margin-top: 16px; }
.overview-top, .source-actions, .overview-meta { display:flex; align-items:center; flex-wrap:wrap; gap:12px 18px; }
.overview-top { justify-content:space-between; }.overview-meta { margin-top:16px; font-size:13px; color:var(--at-text-muted); }
.source-actions > a { font-weight:650; }.source-actions i { font-size:12px; }
summary { cursor:pointer; font-weight:600; }.supporting-details { margin-top:18px; padding-top:14px; border-top:1px solid var(--at-border); }
.posting-tools { margin:20px 0; border:1px solid var(--at-border); border-radius:8px; background:var(--at-surface); }.posting-tools > summary { padding:16px 24px; }
.details > div { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 20px; }
.details dd { text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; }
.missing-value { color: var(--at-cancelled); }
.text-block { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.6; }
.text-block:last-child { margin-bottom: 0; }
fieldset { border: 0; padding: 0; margin: 24px 0; min-width: 0; }
legend { font-weight: 650; margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
label { font-size: 14px; font-weight: 600; }
input, select, textarea { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid var(--at-border); border-radius: 5px; font: inherit; font-weight: 400; background: var(--at-surface); color: var(--at-text); }
textarea { resize: vertical; }
input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid var(--at-focus); outline-offset: 2px; }
.long-field { display: block; margin-top: 18px; }
.hint { font-size: 13px; color: var(--at-text-muted); line-height: 1.5; }
.checkbox { display: flex; align-items: flex-start; gap: 10px; line-height: 1.5; color: var(--at-cancelled); }
.checkbox input { width: auto; margin-top: 3px; }
.check-now { margin-top: 12px; }
.posting-heading { justify-content: space-between; }.posting-heading button:disabled { cursor: not-allowed; }.posting-heading button.is-loading { cursor: wait; }.posting-details { margin-top:16px; }.posting-live { color:var(--at-successful) }.posting-closed { color:var(--at-unsuccessful) }.posting-unknown { color:var(--at-cancelled) }
.success { color: var(--at-successful); font-size: 14px; }
.badge { display: inline-block; background: color-mix(in srgb, var(--at-submitted) 10%, var(--at-surface)); color: var(--at-submitted); font-size: 12px; font-weight: 700; padding: 5px 8px; border-radius: 4px; }
.interview { background: color-mix(in srgb, var(--at-interview) 10%, var(--at-surface)); color: var(--at-interview); } .closed, .withdrawn, .ghosted { background: var(--at-surface-muted); color: var(--at-text-muted); }
.successful { background: color-mix(in srgb, var(--at-successful) 10%, var(--at-surface)); color: var(--at-successful); } .unsuccessful { background: color-mix(in srgb, var(--at-unsuccessful) 10%, var(--at-surface)); color: var(--at-unsuccessful); } .job_cancelled { background: color-mix(in srgb, var(--at-cancelled) 10%, var(--at-surface)); color: var(--at-cancelled); }
@media (max-width: 600px) { .grid { grid-template-columns: 1fr; } .details > div { grid-template-columns: 1fr; gap: 5px; } .panel { padding: 18px; } .focus-heading { align-items: flex-start; flex-wrap: wrap; } }
}
</style>
