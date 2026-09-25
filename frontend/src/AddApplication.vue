<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { createApplication, type Application, type DuplicateMatch } from './api'
import { contactTypes, detectJobSource, jobSources, remotePolicies, type ContactType, type JobSource, type RemotePolicy } from './applicationOptions'

function today() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function blankForm() {
  return {
    job_title: '', company: '', date_applied: today(), job_url: '', email_reference: '',
    contact_type: 'EMAIL' as ContactType, phone_number: '', location: '',
    remote_policy: '' as RemotePolicy | '', contract_type: '', source: 'OTHER' as JobSource,
    description: '', requirements: '',
  }
}

const form = reactive(blankForm())
const sourceIsAutomatic = ref(true)
const requiresPostingUrl = computed(() => form.source === 'LINKEDIN' || form.source === 'INDEED')
const saving = ref(false)
const error = ref('')
const saved = ref<Application | null>(null)
const duplicateWarnings = ref<DuplicateMatch[]>([])

watch(() => form.job_url, url => {
  if (sourceIsAutomatic.value) form.source = detectJobSource(url)
})

function useDetectedSource() {
  sourceIsAutomatic.value = true
  form.source = detectJobSource(form.job_url)
}

function addAnother() {
  Object.assign(form, blankForm())
  sourceIsAutomatic.value = true
  saved.value = null
  duplicateWarnings.value = []
  error.value = ''
}

async function submit() {
  if (saving.value) return
  error.value = ''
  if (!form.job_url.trim() && !form.email_reference.trim()) {
    error.value = 'Provide a job URL or an email reference.'
    return
  }
  if (requiresPostingUrl.value && !form.job_url.trim()) {
    error.value = 'An exact job URL is required for LinkedIn or Indeed applications so the posting can be checked.'
    return
  }
  if (requiresPostingUrl.value && detectJobSource(form.job_url) !== form.source) {
    error.value = 'Use a direct posting URL on the selected LinkedIn or Indeed job board.'
    return
  }
  if (form.contact_type === 'PHONE' && !form.phone_number.trim()) {
    error.value = 'Provide a phone number when contact type is phone.'
    return
  }
  saving.value = true
  try {
    const application = await createApplication({
      job_title: form.job_title.trim(), company: form.company.trim(), date_applied: form.date_applied,
      job_url: form.job_url.trim() || null, email_reference: form.email_reference.trim() || null,
      contact_type: form.contact_type, phone_number: form.phone_number.trim() || null,
      location: form.location.trim() || null, remote_policy: form.remote_policy || null,
      contract_type: form.contract_type.trim() || null, source: form.source,
      description: form.description.trim() || null, requirements: form.requirements.trim() || null,
    })
    saved.value = application
    duplicateWarnings.value = application.duplicate_warnings
  } catch (reason) {
    error.value = reason instanceof TypeError || (reason instanceof Error && reason.name === 'AbortError')
      ? 'Could not confirm the save. Check the applications list before retrying to avoid a duplicate. Your entries have been kept.'
      : reason instanceof Error ? reason.message : 'Unable to save the application.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section aria-labelledby="add-application-title">
    <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#/applications">Applications</a><span aria-hidden="true">/</span><span aria-current="page">Add application</span></nav>
    <p class="eyebrow">Applications / New</p>
    <h2 id="add-application-title">Add application</h2>
    <p class="intro">Record a submitted role and keep its source and contact details together.</p>

    <section v-if="saved" class="saved-panel" aria-live="polite">
      <h3>Application saved</h3>
      <p>{{ saved.job_title }} at {{ saved.company }} is in your tracker.</p>
      <aside v-if="duplicateWarnings.length" class="duplicate-warning"><strong>Possible duplicate{{ duplicateWarnings.length === 1 ? '' : 's' }} found.</strong><p>Compare this record with:</p><ul><li v-for="match in duplicateWarnings" :key="match.id"><a :href="`#/applications/${match.id}`">{{ match.job_title }} at {{ match.company }}</a> · {{ match.date_applied }}</li></ul></aside>
      <div class="actions"><a class="primary action-link" :href="`#/applications/${saved.id}`">View application</a><button type="button" @click="addAnother">Add another</button><a href="#/applications">All applications</a></div>
    </section>

    <form v-else class="application-form" @submit.prevent="submit">
      <fieldset :disabled="saving"><legend>Role details</legend>
        <div class="form-grid">
          <label>Job title <span>(required)</span><input v-model="form.job_title" name="job_title" required maxlength="300" autocomplete="off" /></label>
          <label>Company <span>(required)</span><input v-model="form.company" name="company" required maxlength="300" autocomplete="organization" /></label>
          <label>Date applied <span>(required)</span><input v-model="form.date_applied" name="date_applied" type="date" required /></label>
          <label>Location<input v-model="form.location" name="location" maxlength="300" /></label>
          <label>Remote policy<select v-model="form.remote_policy" name="remote_policy"><option value="">Select policy</option><option v-for="option in remotePolicies" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          <label>Contract type<input v-model="form.contract_type" name="contract_type" maxlength="300" /></label>
        </div>
      </fieldset>
      <fieldset :disabled="saving"><legend>Posting and source</legend>
        <p class="hint">Provide a job URL or an email reference. LinkedIn and Indeed records require their exact job URL so the tracker can check the posting later.</p>
        <div class="form-grid">
          <label>Job URL<input v-model="form.job_url" name="job_url" type="url" placeholder="https://…" maxlength="2048" :required="requiresPostingUrl" /></label>
          <label>Email reference<input v-model="form.email_reference" name="email_reference" placeholder="Message link, ID, or subject" maxlength="2048" /></label>
          <label>Source<select v-model="form.source" name="source" @change="sourceIsAutomatic = false"><option v-for="option in jobSources" :key="option.value" :value="option.value">{{ option.label }}</option></select><small>{{ sourceIsAutomatic ? 'Detected from the job URL when possible.' : 'Selected manually.' }} <button v-if="!sourceIsAutomatic" class="inline-action" type="button" @click="useDetectedSource">Use detected source</button></small></label>
        </div>
      </fieldset>
      <fieldset :disabled="saving"><legend>Contact</legend>
        <div class="form-grid">
          <label>Contact type<select v-model="form.contact_type" name="contact_type"><option v-for="option in contactTypes" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          <label>Phone number <span>{{ form.contact_type === 'PHONE' ? '(required for phone contact)' : '(optional)' }}</span><input v-model="form.phone_number" name="phone_number" type="tel" autocomplete="tel" placeholder="+33 6 12 34 56 78" :required="form.contact_type === 'PHONE'" /><small>French number or +country code for other countries.</small></label>
        </div>
      </fieldset>
      <fieldset :disabled="saving"><legend>Notes about the role</legend>
        <div class="form-grid"><label>Description<textarea v-model="form.description" name="description" rows="4"></textarea></label><label>Requirements<textarea v-model="form.requirements" name="requirements" rows="4"></textarea></label></div>
      </fieldset>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions"><button class="primary" type="submit" :disabled="saving">{{ saving ? 'Saving…' : 'Save application' }}</button><a href="#/applications">Cancel</a></div>
    </form>
  </section>
</template>

<style scoped>
.breadcrumbs { display:flex; align-items:center; gap:9px; color:#627084; font-size:13px; margin-bottom:28px; }
.breadcrumbs a, .actions a { color:#24568b; text-underline-offset:3px; }
.application-form, .saved-panel { background:#fff; border:1px solid #dce2e9; border-radius:10px; padding:28px; max-width:900px; }
fieldset { border:0; border-bottom:1px solid #e5e9ee; padding:0 0 25px; margin:0 0 25px; min-width:0; }
fieldset:last-of-type { border-bottom:0; margin-bottom:0; }
legend { font-size:17px; font-weight:650; margin-bottom:17px; }
.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
label { display:block; font-size:14px; font-weight:600; }
label span, small, .hint { color:#627084; font-size:12px; font-weight:400; }
small { display:block; line-height:1.5; margin-top:5px; }
.hint { font-size:13px; margin:0 0 15px; }
input, select, textarea { display:block; width:100%; min-width:0; border:1px solid #b9c4d2; border-radius:6px; padding:10px; margin-top:7px; font:inherit; font-weight:400; color:#202c3d; background:#fff; }
textarea { resize:vertical; }
input:focus-visible, select:focus-visible, textarea:focus-visible { outline:3px solid #527ba8; outline-offset:2px; }
.actions { display:flex; align-items:center; flex-wrap:wrap; gap:15px; margin-top:12px; }
.primary { background:#263e5c; border-color:#263e5c; color:#fff; }
.primary:hover:enabled { background:#192d45; }
.action-link { display:inline-flex; align-items:center; min-height:40px; padding:9px 13px; border-radius:6px; text-decoration:none; }
.actions .action-link { color:#fff; }
.inline-action { border:0; padding:0; font-size:12px; color:#24568b; text-decoration:underline; }
.duplicate-warning { background:#fff1de; border:1px solid #f0d4ae; border-radius:6px; padding:15px; margin:18px 0; font-size:14px; }
.duplicate-warning p { margin:6px 0; }.duplicate-warning ul { margin:8px 0 0; padding-left:20px; }
@media (max-width:650px) { .form-grid { grid-template-columns:1fr; }.application-form,.saved-panel { padding:20px; } }
</style>
