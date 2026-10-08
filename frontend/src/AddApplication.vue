<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import Stepper from 'primevue/stepper'
import StepList from 'primevue/steplist'
import Step from 'primevue/step'
import StepPanels from 'primevue/steppanels'
import StepPanel from 'primevue/steppanel'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Checkbox from 'primevue/checkbox'
import Button from 'primevue/button'
import SuggestionField from './components/shared/SuggestionField.vue'
import DatePicker from './DatePicker.vue'
import NumberField from './components/shared/NumberField.vue'
import { createApplication, validateContact, type Application, type DuplicateMatch } from './api'
import { contactTypes, detectJobSource, jobSources, remotePolicies, remotePolicyLabel, jobSourceLabel } from './applicationOptions'
import { applicationPayload, blankApplicationDraft, blankWizardOptions, wizardErrors } from './applicationWizard'
import { addressBookError, addressBookLoading, loadAddressBook, rememberApplication, savedContacts, suggestions } from './settings/applicationAddressBook'

const form = reactive(blankApplicationDraft())
const options = reactive(blankWizardOptions())
const currentStep = ref('1')
const steps = [{ value: '1', label: 'Role', icon: 'pi pi-briefcase' }, { value: '2', label: 'Posting', icon: 'pi pi-link' }, { value: '3', label: 'Contact & extras', icon: 'pi pi-address-book' }, { value: '4', label: 'Review', icon: 'pi pi-check-circle' }]
const sourceIsAutomatic = ref(true)
const saving = ref(false)
const checking = ref(false)
const error = ref('')
const errors = reactive<Record<string, string>>({})
const saved = ref<Application | null>(null)
const duplicateWarnings = ref<DuplicateMatch[]>([])
const selectedContact = ref<string | null>(null)
const wizardElement = ref<HTMLElement | null>(null)
const showEmail = computed(() => options.contact && (form.contact_type === 'EMAIL' || options.extraContact))
const showPhone = computed(() => options.contact && (form.contact_type === 'PHONE' || options.extraContact))
const payload = computed(() => applicationPayload(form, options))
const deadlineOptions = [{ value: 'APPLICATION_CLOSING', label: 'Applications close' }, { value: 'FIRST_ROUND', label: 'First-round selection' }]
watch(() => form.job_url, url => { if (sourceIsAutomatic.value) form.source = detectJobSource(url) })
watch(() => form.contact_type, () => { options.extraContact = false; delete errors.contact_email; delete errors.phone_number })
watch(() => [options.contact, options.extraContact], () => {
  if (!showEmail.value) { contactVersions.contact_email++; delete errors.contact_email }
  if (!showPhone.value) { contactVersions.phone_number++; delete errors.phone_number }
})
onMounted(() => { void loadAddressBook() })

function useDetectedSource() { sourceIsAutomatic.value = true; form.source = detectJobSource(form.job_url) }
function clearErrors() { for (const key of Object.keys(errors)) delete errors[key]; error.value = '' }
async function goToStep(value: string) {
  currentStep.value = value
  clearErrors()
  await nextTick()
  wizardElement.value?.querySelector<HTMLElement>(`#wizard-step-${value}`)?.focus()
}
function useContact(id: string) {
  const contact = savedContacts.value.find(item => item.value === id)?.record
  if (!contact) return
  form.contact_type = contact.contact_email ? contact.contact_type : 'PHONE'
  form.contact_name = contact.contact_name || ''
  form.contact_email = contact.contact_email || ''
  form.phone_number = contact.phone_number || ''
  // Run after the contact-type watcher so both saved methods remain visible.
  void nextTick(() => { options.extraContact = Boolean(form.contact_email && form.phone_number) })
}
const contactVersions = { contact_email: 0, phone_number: 0 }
async function checkContact(field: 'contact_email' | 'phone_number'): Promise<boolean> {
  const version = ++contactVersions[field]
  const raw = form[field]
  if (!raw.trim()) { delete errors[field]; return true }
  try {
    await validateContact({ contact_email: field === 'contact_email' ? raw.trim() : null, phone_number: field === 'phone_number' ? raw.trim() : null })
    if (version === contactVersions[field] && raw === form[field]) delete errors[field]
    return true
  } catch (reason) {
    if (version === contactVersions[field] && raw === form[field]) errors[field] = reason instanceof Error ? reason.message : 'Unable to validate this contact.'
    return false
  }
}
async function validateStep(step: number): Promise<boolean> {
  Object.assign(errors, wizardErrors(step, form, options))
  if (step === 3 && options.contact) {
    checking.value = true
    try { await Promise.all([...(showEmail.value && form.contact_email.trim() ? [checkContact('contact_email')] : []), ...(showPhone.value && form.phone_number.trim() ? [checkContact('phone_number')] : [])]) }
    finally { checking.value = false }
  }
  return !Object.values(errors).some(Boolean)
}
async function next() {
  if (saving.value || checking.value) return
  clearErrors()
  if (await validateStep(Number(currentStep.value))) await goToStep(String(Number(currentStep.value) + 1))
}
function addAnother() {
  Object.assign(form, blankApplicationDraft())
  Object.assign(options, blankWizardOptions())
  sourceIsAutomatic.value = true
  saved.value = null
  duplicateWarnings.value = []
  selectedContact.value = null
  void goToStep('1')
}
async function submit() {
  if (saving.value || checking.value) return
  if (currentStep.value !== '4') { await next(); return }
  clearErrors()
  for (const step of [1, 2, 3]) {
    if (!await validateStep(step)) { currentStep.value = String(step); return }
  }
  saving.value = true
  try {
    const application = await createApplication(payload.value)
    saved.value = application
    duplicateWarnings.value = application.duplicate_warnings
    rememberApplication(application)
  } catch (reason) {
    error.value = reason instanceof TypeError || (reason instanceof Error && reason.name === 'AbortError')
      ? 'Could not confirm the save. Check the applications list before retrying to avoid a duplicate. Your entries have been kept.'
      : reason instanceof Error ? reason.message : 'Unable to save the application.'
  } finally { saving.value = false }
}
</script>

<template>
  <section aria-labelledby="add-application-title">
    <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#/applications">Applications</a><span aria-hidden="true">/</span><span aria-current="page">Add application</span></nav>
    <p class="eyebrow">Your next opportunity</p>
    <h2 id="add-application-title">Add application</h2>
    <p class="intro">A few small steps to capture the role, its source, and what comes next.</p>
    <section v-if="saved" class="wizard-card saved-panel" aria-live="polite">
      <i class="pi pi-check-circle success-icon" aria-hidden="true" /><h3>Application saved</h3><p>{{ saved.job_title }} at {{ saved.company }} is in your tracker.</p>
      <aside v-if="duplicateWarnings.length" class="at-message warning"><strong>Possible duplicate{{ duplicateWarnings.length === 1 ? '' : 's' }} found.</strong><ul><li v-for="match in duplicateWarnings" :key="match.id"><a :href="`#/applications/${match.id}`">{{ match.job_title }} at {{ match.company }}</a> · {{ match.date_applied }}</li></ul></aside>
      <div class="wizard-actions"><Button as="a" :href="`#/applications/${saved.id}`" label="View application" icon="pi pi-arrow-right" /><Button label="Add another" severity="secondary" outlined icon="pi pi-plus" @click="addAnother" /></div>
    </section>
    <form v-else ref="wizardElement" class="wizard-card" novalidate aria-label="Add application wizard" @submit.prevent="submit">
      <p v-if="addressBookError" class="at-message warning" role="status">{{ addressBookError }} <Button type="button" label="Retry suggestions" text :disabled="addressBookLoading" @click="loadAddressBook" /></p>
      <Stepper v-model:value="currentStep" linear>
        <StepList><Step v-for="step in steps" :key="step.value" :value="step.value"><i :class="step.icon" aria-hidden="true" /><span>{{ step.label }}</span></Step></StepList>
        <StepPanels>
          <StepPanel value="1">
            <h3 id="wizard-step-1" class="step-heading" tabindex="-1">Which role did you apply for?</h3><p class="step-intro">Start with the essentials. Type to find values from your application address book, or enter something new.</p>
            <div class="form-grid">
              <SuggestionField v-model="form.job_title" label="Job title" :suggestions="suggestions.job_title" :error="errors.job_title" :disabled="saving || checking" required />
              <SuggestionField v-model="form.company" label="Company" :suggestions="suggestions.company" :error="errors.company" :disabled="saving || checking" required />
              <div><DatePicker v-model="form.date_applied" label="Date applied" required :disabled="saving || checking" /><Select v-if="suggestions.date_applied.length" :model-value="null" :options="suggestions.date_applied" filter aria-label="Reuse an application date" placeholder="Previous dates…" :disabled="saving || checking" class="at-form-control" @update:model-value="form.date_applied = $event" /><small v-if="errors.date_applied" class="field-error" role="alert">{{ errors.date_applied }}</small></div>
              <SuggestionField v-model="form.location" label="Location" :suggestions="suggestions.location" :disabled="saving || checking" placeholder="City, region, or remote" />
            </div>
            <div class="remote-field"><label id="remote-policy-label">Remote policy <span>(optional)</span></label><SelectButton v-model="form.remote_policy" :options="remotePolicies" option-label="label" option-value="value" aria-labelledby="remote-policy-label" :disabled="saving || checking" /><small>{{ form.remote_policy ? remotePolicyLabel(form.remote_policy) : 'Not specified' }} · Click the selected option again to clear it.</small></div>
            <details class="optional-panel"><summary><i class="pi pi-sliders-h" aria-hidden="true" /> More role details</summary><div class="optional-content"><SuggestionField v-model="form.contract_type" label="Contract type" :suggestions="suggestions.contract_type" :disabled="saving || checking" /><label class="toggle"><Checkbox v-model="options.intermediary" binary input-id="has-intermediary" :disabled="saving || checking" /><span>A recruiter, school, or agency forwarded this application</span></label><SuggestionField v-if="options.intermediary" v-model="form.intermediary" label="Via / intermediary" :suggestions="suggestions.intermediary" :disabled="saving || checking" hint="Keep the actual employer in Company. Use Employer not disclosed if it is unknown." /></div></details>
          </StepPanel>
          <StepPanel value="2">
            <h3 id="wizard-step-2" class="step-heading" tabindex="-1">Keep the posting and its evidence</h3><p class="step-intro">Add a job URL, an email reference, or both so you can find this opportunity again.</p>
            <div class="form-grid"><SuggestionField v-model="form.job_url" label="Posting URL" :suggestions="suggestions.job_url" :error="errors.job_url" :disabled="saving || checking" :maxlength="2048" type="url" placeholder="https://…" /><SuggestionField v-model="form.email_reference" label="Application email reference" :suggestions="suggestions.email_reference" :disabled="saving || checking" :maxlength="2048" hint="A message link, ID, or subject. This is different from the recruiter's email address." /></div>
            <div class="source-field"><label for="wizard-source">Source</label><Select v-model="form.source" input-id="wizard-source" :options="jobSources" option-label="label" option-value="value" :disabled="saving || checking" class="at-form-control" @change="sourceIsAutomatic = false" /><small>{{ sourceIsAutomatic ? 'Detected from the posting URL when possible.' : 'Selected manually.' }}</small><Button v-if="!sourceIsAutomatic" type="button" label="Use detected source" severity="secondary" text size="small" @click="useDetectedSource" /></div>
            <label class="toggle"><Checkbox v-model="options.deadline" binary input-id="has-deadline" :disabled="saving || checking" /><span>This posting has a deadline or first-round selection date</span></label>
            <div v-if="options.deadline" class="form-grid optional-content"><div><DatePicker v-model="form.deadline" label="Deadline" required :disabled="saving || checking" /><Select v-if="suggestions.deadline.length" :model-value="null" :options="suggestions.deadline" filter aria-label="Reuse a deadline date" placeholder="Previous deadlines…" :disabled="saving || checking" class="at-form-control" @update:model-value="form.deadline = $event" /><small v-if="errors.deadline" class="field-error" role="alert">{{ errors.deadline }}</small></div><div><label for="deadline-kind">What happens on this date?</label><Select v-model="form.deadline_kind" input-id="deadline-kind" :options="deadlineOptions" option-label="label" option-value="value" :disabled="saving || checking" class="at-form-control" /></div></div>
          </StepPanel>
          <StepPanel value="3">
            <h3 id="wizard-step-3" class="step-heading" tabindex="-1">Add only the details you need</h3><p class="step-intro">Contact information, notes, and reminder overrides are optional.</p>
            <label class="toggle"><Checkbox v-model="options.contact" binary input-id="has-contact" :disabled="saving || checking" /><span>I have a contact for this application</span></label>
            <div v-if="options.contact" class="optional-content contact-card">
              <div v-if="savedContacts.length"><label for="saved-contact">Reuse a contact from your address book</label><Select v-model="selectedContact" input-id="saved-contact" :options="savedContacts" option-label="label" option-value="value" filter show-clear placeholder="Choose a saved contact…" class="at-form-control" :disabled="saving || checking" @update:model-value="useContact" /><small>Contact details are reused only when you select them.</small></div>
              <SuggestionField v-model="form.contact_name" label="Contact name" :suggestions="suggestions.contact_name" :disabled="saving || checking" />
              <div><label id="contact-method-label">Preferred contact method</label><SelectButton v-model="form.contact_type" :options="contactTypes" option-label="label" option-value="value" :allow-empty="false" aria-labelledby="contact-method-label" :disabled="saving || checking" /></div>
              <div class="form-grid"><SuggestionField v-if="showEmail" v-model="form.contact_email" label="Contact email" :suggestions="suggestions.contact_email" :maxlength="320" type="email" placeholder="name@company.com" :required="form.contact_type === 'EMAIL'" :error="errors.contact_email" :disabled="saving || checking" @blur="checkContact('contact_email')" /><SuggestionField v-if="showPhone" v-model="form.phone_number" label="Phone number" :suggestions="suggestions.phone_number" :maxlength="30" type="tel" placeholder="+33 6 12 34 56 78" :required="form.contact_type === 'PHONE'" :error="errors.phone_number" :disabled="saving || checking" hint="French national numbers or an international +country code. Saved in international format." @blur="checkContact('phone_number')" /></div>
              <label class="toggle"><Checkbox v-model="options.extraContact" binary input-id="extra-contact" :disabled="saving || checking" /><span>Also add {{ form.contact_type === 'EMAIL' ? 'a phone number' : 'an email address' }}</span></label>
            </div>
            <details class="optional-panel"><summary><i class="pi pi-file-edit" aria-hidden="true" /> Notes about the role</summary><div class="optional-content"><label class="toggle"><Checkbox v-model="options.notes" binary input-id="has-notes" :disabled="saving || checking" /><span>Include description and requirements</span></label><div v-if="options.notes" class="form-grid"><SuggestionField v-model="form.description" label="Description" :suggestions="suggestions.description" :maxlength="50000" multiline :disabled="saving || checking" /><SuggestionField v-model="form.requirements" label="Requirements" :suggestions="suggestions.requirements" :maxlength="50000" multiline :disabled="saving || checking" /></div></div></details>
            <details class="optional-panel"><summary><i class="pi pi-bell" aria-hidden="true" /> Follow-up preferences</summary><div class="optional-content"><p class="step-intro">Leave these blank to use your global follow-up preferences.</p><label class="toggle"><Checkbox v-model="options.followups" binary input-id="custom-followups" :disabled="saving || checking" /><span>Customize reminders for this application</span></label><div v-if="options.followups" class="form-grid"><div><NumberField v-model="form.followup_delay_days" label="Follow-up delay (days)" :disabled="saving || checking" :min="0" :max="3650" placeholder="Global default" /><Select v-if="suggestions.followup_delay_days.length" :model-value="null" :options="suggestions.followup_delay_days" :disabled="saving || checking" aria-label="Reuse a follow-up delay" placeholder="Previous values…" class="at-form-control" @update:model-value="form.followup_delay_days = Number($event)" /><small v-if="errors.followup_delay_days" class="field-error">{{ errors.followup_delay_days }}</small></div><div><NumberField v-model="form.max_followup_suggestions" label="Automatic reminder limit" :disabled="saving || checking" :min="0" :max="100" placeholder="Global default" /><Select v-if="suggestions.max_followup_suggestions.length" :model-value="null" :options="suggestions.max_followup_suggestions" :disabled="saving || checking" aria-label="Reuse a reminder limit" placeholder="Previous values…" class="at-form-control" @update:model-value="form.max_followup_suggestions = Number($event)" /><small v-if="errors.max_followup_suggestions" class="field-error">{{ errors.max_followup_suggestions }}</small></div></div></div></details>
          </StepPanel>
          <StepPanel value="4">
            <h3 id="wizard-step-4" class="step-heading" tabindex="-1">Ready to add this opportunity?</h3><p class="step-intro">Check the details below. You can go back to any screen before saving.</p>
            <div class="review-card"><div class="review-heading"><i class="pi pi-briefcase" aria-hidden="true" /><div><h3>{{ form.job_title }}</h3><p>{{ form.company }}<template v-if="form.location"> · {{ form.location }}</template></p></div><Button type="button" label="Edit role" severity="secondary" text @click="goToStep('1')" /></div><dl><div><dt>Applied</dt><dd>{{ form.date_applied }}</dd></div><div v-if="form.remote_policy"><dt>Remote policy</dt><dd>{{ remotePolicyLabel(form.remote_policy) }}</dd></div><div v-if="payload.contract_type"><dt>Contract</dt><dd>{{ payload.contract_type }}</dd></div><div v-if="payload.intermediary"><dt>Via</dt><dd>{{ payload.intermediary }}</dd></div></dl></div>
            <div class="review-card"><div class="review-heading"><h3>Posting</h3><Button type="button" label="Edit posting" severity="secondary" text @click="goToStep('2')" /></div><dl><div><dt>Source</dt><dd>{{ jobSourceLabel(form.source) }}</dd></div><div v-if="payload.job_url"><dt>Posting URL</dt><dd>{{ payload.job_url }}</dd></div><div v-if="payload.email_reference"><dt>Email reference</dt><dd>{{ payload.email_reference }}</dd></div><div v-if="payload.deadline"><dt>{{ payload.deadline_kind === 'FIRST_ROUND' ? 'First-round selection' : 'Applications close' }}</dt><dd>{{ payload.deadline }}</dd></div></dl></div>
            <div class="review-card"><div class="review-heading"><h3>Contact & extras</h3><Button type="button" label="Edit extras" severity="secondary" text @click="goToStep('3')" /></div><p v-if="!options.contact">No contact added.</p><dl v-else><div><dt>Preferred method</dt><dd>{{ form.contact_type === 'EMAIL' ? 'Email' : 'Phone' }}</dd></div><div v-if="payload.contact_name"><dt>Name</dt><dd>{{ payload.contact_name }}</dd></div><div v-if="payload.contact_email"><dt>Email</dt><dd>{{ payload.contact_email }}</dd></div><div v-if="payload.phone_number"><dt>Phone</dt><dd>{{ payload.phone_number }}</dd></div></dl><p v-if="payload.description || payload.requirements">Role notes included.</p><p>{{ options.followups ? 'Custom' : 'Default' }} follow-up preferences.</p></div>
          </StepPanel>
        </StepPanels>
      </Stepper>
      <p v-if="error" class="at-message error" role="alert">{{ error }}</p>
      <div class="wizard-actions"><Button v-if="currentStep !== '1'" type="button" label="Back" icon="pi pi-arrow-left" severity="secondary" outlined :disabled="saving || checking" @click="goToStep(String(Number(currentStep) - 1))" /><a href="#/applications">Cancel</a><span class="step-count" aria-live="polite">Step {{ currentStep }} of 4</span><Button type="submit" :label="saving ? 'Saving…' : checking ? 'Checking contact…' : currentStep === '4' ? 'Save application' : 'Continue'" :icon="currentStep === '4' ? 'pi pi-check' : 'pi pi-arrow-right'" icon-pos="right" :disabled="saving || checking" /></div>
    </form>
  </section>
</template>
<style scoped>
.breadcrumbs { display:flex; align-items:center; gap:9px; color:var(--at-text-muted); font-size:13px; margin-bottom:24px; }
.wizard-card { max-width:960px; background:var(--at-surface); border:1px solid var(--at-border); border-radius:14px; padding:24px; }
.step-heading { margin:8px 0 10px; font-size:22px; }.step-heading:focus { outline:none; }.step-intro { color:var(--at-text-muted); font-size:14px; line-height:1.6; margin:0 0 24px; }
.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; }.form-grid > div { min-width:0; }
label { display:block; font-size:14px; font-weight:600; }label span:not(.p-checkbox) { font-weight:400; }small { display:block; font-size:12px; color:var(--at-text-muted); line-height:1.5; margin:6px 0; }.field-error { color:var(--at-unsuccessful); }
.remote-field { margin:24px 0; }.remote-field label { margin-bottom:10px; }.remote-field label span { color:var(--at-text-muted); font-size:12px; }.remote-field :deep(.p-selectbutton) { display:inline-flex; flex-wrap:wrap; }
.optional-panel { border:1px solid var(--at-border); background:var(--at-background); border-radius:8px; margin:20px 0; }summary { cursor:pointer; padding:16px; font-size:14px; font-weight:600; }summary i { margin-right:8px; }.optional-content { padding:16px; }.optional-content > .suggestion-field, .contact-card > div { margin-bottom:18px; }
.toggle { display:flex; align-items:center; gap:10px; font-size:14px; margin:20px 0; cursor:pointer; }.source-field { max-width:390px; margin:24px 0; }.contact-card { border:1px solid var(--at-border); border-radius:8px; }
.wizard-actions { display:flex; align-items:center; flex-wrap:wrap; gap:14px; padding-top:22px; margin-top:14px; border-top:1px solid var(--at-border); }.step-count { margin-left:auto; color:var(--at-text-muted); font-size:12px; }
.review-card { padding:18px; border:1px solid var(--at-border); border-radius:8px; margin:14px 0; }.review-heading { display:flex; align-items:center; gap:12px; }.review-heading .p-button { margin-left:auto; }.review-heading i { color:var(--at-primary); font-size:24px; }.review-card p { color:var(--at-text-muted); font-size:14px; }dd { overflow-wrap:anywhere; }.success-icon { color:var(--at-successful); font-size:32px; margin-bottom:16px; }
:deep(.p-step-title) { display:flex; gap:7px; align-items:center; }:deep(.p-step-title i) { font-size:14px; }
@media (max-width:650px) { .wizard-card { padding:16px; }.form-grid { grid-template-columns:1fr; }:deep(.p-step-title) { font-size:11px; flex-direction:column; }:deep(.p-step-number) { width:26px; height:26px; min-width:26px; font-size:12px; }:deep(.p-step-header) { gap:5px; padding:8px 3px; }.wizard-actions { gap:10px; }.step-count { width:100%; order:-1; margin:0; }.review-heading { flex-wrap:wrap; } }
</style>
