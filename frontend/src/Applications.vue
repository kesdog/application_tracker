<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createApplication, listApplications, type Application } from './api'

const applications = ref<Application[]>([])
const loading = ref(false)
const saving = ref(false)
const showForm = ref(false)
const loadError = ref('')
const formError = ref('')
const success = ref('')
function today() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
const form = reactive({ job_title: '', company: '', date_applied: today(), job_url: '', email_reference: '' })

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    applications.value = await listApplications()
  } catch {
    loadError.value = 'Unable to load applications. Check that the backend is running, then refresh the list.'
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (saving.value) return
  formError.value = ''
  success.value = ''
  if (!form.job_url.trim() && !form.email_reference.trim()) {
    formError.value = 'Provide a job URL or an email reference.'
    return
  }
  saving.value = true
  try {
    const application = await createApplication({
      job_title: form.job_title.trim(), company: form.company.trim(), date_applied: form.date_applied,
      job_url: form.job_url.trim() || null, email_reference: form.email_reference.trim() || null,
    })
    applications.value.push(application)
    applications.value.sort((a, b) => b.date_applied.localeCompare(a.date_applied) || a.id.localeCompare(b.id))
    success.value = `Saved ${application.job_title} at ${application.company}.`
    Object.assign(form, { job_title: '', company: '', date_applied: today(), job_url: '', email_reference: '' })
    showForm.value = false
  } catch (error) {
    formError.value = error instanceof TypeError || (error instanceof Error && error.name === 'AbortError')
      ? 'Could not confirm the save. Refresh the list before retrying to avoid a duplicate. Your form entries have been kept.'
      : error instanceof Error ? error.message : 'Unable to save the application.'
  } finally {
    saving.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section aria-labelledby="applications-title">
    <div class="page-heading">
      <div><p class="eyebrow">Your workspace</p><h2 id="applications-title">Applications</h2></div>
      <button v-if="!showForm" class="primary" type="button" @click="showForm = true; success = ''; formError = ''">Add application</button>
    </div>
    <p class="intro">Keep track of the roles you have applied for.</p>
    <p v-if="success" class="success" role="status">{{ success }}</p>

    <form v-if="showForm" class="application-form" @submit.prevent="submit">
      <h3>New application</h3>
      <fieldset :disabled="saving">
        <legend class="sr-only">Application details</legend>
        <div class="form-grid">
          <label>Job title <span>(required)</span><input v-model="form.job_title" name="job_title" required maxlength="300" autocomplete="off" /></label>
          <label>Company <span>(required)</span><input v-model="form.company" name="company" required maxlength="300" autocomplete="organization" /></label>
          <label>Date applied <span>(required)</span><input v-model="form.date_applied" name="date_applied" type="date" required /></label>
        </div>
        <p id="source-help" class="source-help">Provide at least one source: a job URL or an email reference.</p>
        <div class="form-grid">
          <label>Job URL<input v-model="form.job_url" name="job_url" type="url" placeholder="https://…" maxlength="2048" aria-describedby="source-help" /></label>
          <label>Email reference<input v-model="form.email_reference" name="email_reference" placeholder="Message link, ID, or subject" maxlength="2048" aria-describedby="source-help" /></label>
        </div>
      </fieldset>
      <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      <div class="form-actions">
        <button class="primary" type="submit" :disabled="saving || loading">{{ saving ? 'Saving…' : 'Save application' }}</button>
        <button type="button" :disabled="saving" @click="showForm = false">Cancel</button>
      </div>
    </form>

    <div class="list-heading"><span>{{ applications.length }} {{ applications.length === 1 ? 'application' : 'applications' }}</span><button type="button" :disabled="loading || saving" @click="refresh">{{ loading ? 'Loading…' : 'Refresh list' }}</button></div>
    <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
    <div class="table-panel" :aria-busy="loading">
      <p v-if="loading && !applications.length" class="empty" role="status">Loading applications…</p>
      <p v-else-if="!applications.length && !loadError" class="empty">No applications yet. Add your first submitted application to get started.</p>
      <div v-else-if="applications.length" class="table-scroll" tabindex="0" role="region" aria-label="Applications table">
        <table>
          <caption class="sr-only">Submitted applications, newest applied date first</caption>
          <thead><tr><th scope="col">Date applied</th><th scope="col">Company</th><th scope="col">Position</th><th scope="col">Status</th><th scope="col">Source</th></tr></thead>
          <tbody><tr v-for="application in applications" :key="application.id">
            <td class="date-cell">{{ application.date_applied }}</td><td>{{ application.company }}</td><td>{{ application.job_title }}</td>
            <td><span class="status-badge">{{ application.status }}</span></td>
            <td class="source-cell"><a v-if="application.job_url" :href="application.job_url" target="_blank" rel="noopener noreferrer">Job posting ↗</a><span v-if="application.email_reference" class="email-reference">{{ application.email_reference }}</span></td>
          </tr></tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page-heading, .list-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.primary { background: #263e5c; border-color: #263e5c; color: #fff; }
.primary:hover:enabled { background: #192d45; }
.application-form { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 24px; margin-bottom: 24px; }
fieldset { border: 0; padding: 0; margin: 20px 0; min-width: 0; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
label { display: block; font-size: 14px; font-weight: 600; }
label span { color: #576678; font-size: 12px; font-weight: 400; }
input { display: block; width: 100%; min-width: 0; border: 1px solid #b9c4d2; border-radius: 5px; padding: 10px; margin-top: 7px; font: inherit; font-weight: 400; color: #202c3d; background: #fff; }
input:focus-visible, .table-scroll:focus-visible { outline: 3px solid #527ba8; outline-offset: 2px; }
.source-help { font-size: 13px; color: #576678; margin: 22px 0 14px; }
.form-actions { display: flex; gap: 10px; }
.list-heading { margin: 24px 0 12px; font-size: 14px; color: #576678; }
.table-panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; overflow: hidden; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }
th { background: #edf1f5; font-size: 12px; color: #526174; font-weight: 650; white-space: nowrap; }
th, td { padding: 14px 16px; border-bottom: 1px solid #e5e9ee; vertical-align: top; }
td { overflow-wrap: anywhere; min-width: 140px; max-width: 300px; }
tr:last-child td { border-bottom: 0; }
.date-cell { white-space: nowrap; }
.status-badge { display: inline-block; background: #eaf1fc; color: #2a5189; font-size: 11px; font-weight: 700; padding: 4px 7px; border-radius: 4px; }
a { color: #24568b; text-underline-offset: 3px; }
.email-reference { display: block; margin-top: 4px; white-space: pre-wrap; }
.empty { padding: 32px 24px; margin: 0; color: #576678; font-size: 14px; line-height: 1.6; }
.success { color: #216344; padding: 12px 16px; background: #eaf5ee; border-radius: 6px; font-size: 14px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 600px) { .form-grid { grid-template-columns: 1fr; } .application-form { padding: 18px; } .page-heading { align-items: flex-start; } }
</style>
