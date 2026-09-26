<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { applicationExportUrl, listApplications, type Application, type ApplicationFilters } from './api'
import ApplicationFocus from './ApplicationFocus.vue'
import Pagination from './Pagination.vue'
import { jobSourceLabel, jobSources, remotePolicies } from './applicationOptions'

function selectedId() {
  const match = window.location.hash.match(/^#\/applications\/([^/]+)$/)
  return match ? match[1]! : null
}
const focusedId = ref(selectedId())
function navigate() {
  focusedId.value = selectedId()
  if (!focusedId.value) void refresh()
}

const applications = ref<Application[]>([])
const loading = ref(false)
const loadError = ref('')
const exportFormat = ref<'csv' | 'xlsx'>('csv')
const statuses = ['', 'SUBMITTED', 'INTERVIEW', 'CLOSED'] as const
const outcomes = ['', 'SUCCESSFUL', 'UNSUCCESSFUL', 'WITHDRAWN', 'JOB_CANCELLED', 'GHOSTED'] as const
const blankFilters = (): ApplicationFilters => ({ q: '', status: '', outcome: '', company: '', title: '', location: '', contract_type: '', source: '', remote_policy: '', date_from: '', date_to: '', document_filename: '' })
const filters = reactive<ApplicationFilters>(blankFilters())
const filtersOpen = ref(false)
const page = ref(1)
const pageSize = 10
const hasFilters = computed(() => Object.values(filters).some(Boolean))
const visibleApplications = computed(() => applications.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const exportAllUrl = computed(() => applicationExportUrl(exportFormat.value))
const exportCurrentUrl = computed(() => applicationExportUrl(exportFormat.value, filters))

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    applications.value = await listApplications(filters)
    page.value = 1
  } catch {
    loadError.value = 'Unable to load applications. Check that the backend is running, then refresh the list.'
  } finally {
    loading.value = false
  }
}

function clearFilters() {
  Object.assign(filters, blankFilters())
  page.value = 1
  void refresh()
}

function onInvalidation() {
  if (!focusedId.value) void refresh()
}

onMounted(() => {
  window.addEventListener('hashchange', navigate)
  window.addEventListener('tracker:invalidate', onInvalidation)
  if (!focusedId.value) void refresh()
})
onUnmounted(() => { window.removeEventListener('hashchange', navigate); window.removeEventListener('tracker:invalidate', onInvalidation) })
</script>

<template>
  <ApplicationFocus v-if="focusedId" :key="focusedId" :id="focusedId" />
  <section v-else aria-labelledby="applications-title">
    <div class="page-heading">
      <div><p class="eyebrow">Your workspace</p><h2 id="applications-title">Applications</h2></div>
      <a class="primary add-link" href="#/applications/new">Add application</a>
    </div>
    <p class="intro">Keep track of the roles you have applied for.</p>
    <form class="filters" aria-label="Application filters" @submit.prevent="refresh">
      <div class="filter-heading"><div><h3>Search and filters</h3><p v-if="hasFilters" class="filter-status">Filters applied</p></div><div class="filter-actions"><button v-if="hasFilters" type="button" :disabled="loading" @click="clearFilters">Clear filters</button><button type="button" :aria-expanded="filtersOpen" @click="filtersOpen = !filtersOpen">{{ filtersOpen ? 'Hide filters' : 'Show filters' }}</button></div></div>
      <template v-if="filtersOpen">
      <div class="filter-grid">
        <label class="search-field">Search<input v-model="filters.q" type="search" placeholder="Company, title, description…" /></label>
        <label>Status<select v-model="filters.status"><option v-for="status in statuses" :key="status" :value="status">{{ status || 'Any status' }}</option></select></label>
        <label>Outcome<select v-model="filters.outcome"><option v-for="outcome in outcomes" :key="outcome" :value="outcome">{{ outcome || 'Any outcome' }}</option></select></label>
        <label>Company<input v-model="filters.company" /></label><label>Position<input v-model="filters.title" /></label><label>Location<input v-model="filters.location" /></label>
        <label>Contract type<input v-model="filters.contract_type" /></label><label>Source<select v-model="filters.source"><option value="">Any source</option><option v-for="option in jobSources" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><label>Remote policy<select v-model="filters.remote_policy"><option value="">Any policy</option><option v-for="option in remotePolicies" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <label>Document filename<input v-model="filters.document_filename" placeholder="CV or cover letter filename" /></label>
        <label>Applied from<input v-model="filters.date_from" type="date" /></label><label>Applied to<input v-model="filters.date_to" type="date" /></label>
      </div>
      <button class="primary" type="submit" :disabled="loading">Apply filters</button>
      </template>
    </form>

    <section class="exports" aria-labelledby="exports-title">
      <div><h3 id="exports-title">Export applications</h3><p>Download every application or exactly the current filtered view.</p></div>
      <label>Format<select v-model="exportFormat"><option value="csv">CSV</option><option value="xlsx">XLSX</option></select></label>
      <a class="export-link" :href="exportAllUrl" :download="`applications.${exportFormat}`">Export all</a>
      <a class="export-link primary" :href="exportCurrentUrl" :download="`applications.${exportFormat}`">Export current view</a>
    </section>

    <div class="list-heading"><span>{{ applications.length }} {{ applications.length === 1 ? 'application' : 'applications' }}{{ hasFilters ? ' matched' : '' }}</span><button type="button" :disabled="loading" @click="refresh">{{ loading ? 'Loading…' : 'Refresh list' }}</button></div>
    <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
    <div class="table-panel" :aria-busy="loading">
      <p v-if="loading && !applications.length" class="empty" role="status">Loading applications…</p>
      <p v-else-if="!applications.length && !loadError" class="empty">{{ hasFilters ? 'No applications match these filters.' : 'No applications yet. Add your first submitted application to get started.' }}</p>
      <div v-else-if="applications.length" class="table-scroll" tabindex="0" role="region" aria-label="Applications table">
        <table>
          <caption class="sr-only">Submitted applications, newest applied date first</caption>
          <thead><tr><th scope="col">Date applied</th><th scope="col">Company</th><th scope="col">Position</th><th scope="col">Status</th><th scope="col">Outcome</th><th scope="col">Source</th></tr></thead>
          <tbody><tr v-for="application in visibleApplications" :key="application.id">
            <td class="date-cell">{{ application.date_applied }}</td><td>{{ application.company }}</td><td><a :href="`#/applications/${application.id}`">{{ application.job_title }}</a></td>
            <td><span class="status-badge" :class="application.status.toLowerCase()">{{ application.status }}</span></td>
            <td><span v-if="application.outcome" class="status-badge" :class="application.outcome.toLowerCase()">{{ application.outcome }}</span><span v-else>—</span></td>
            <td class="source-cell"><span>{{ jobSourceLabel(application.source) }}</span><a v-if="application.job_url" :href="application.job_url" target="_blank" rel="noopener noreferrer">Job posting ↗</a><span v-if="application.email_reference" class="email-reference">{{ application.email_reference }}</span></td>
          </tr></tbody>
        </table>
      </div>
      <Pagination v-model:page="page" :total="applications.length" label="applications" />
    </div>
  </section>
</template>

<style scoped>
.page-heading, .list-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.primary { background: #263e5c; border-color: #263e5c; color: #fff; }
.primary:hover:enabled { background: #192d45; }
.add-link { display:inline-flex; align-items:center; min-height:40px; padding:9px 13px; border-radius:6px; text-decoration:none; white-space:nowrap; }
.page-heading .add-link { color:#fff; }
.filters { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 24px; margin-bottom: 24px; }
.exports { display: grid; grid-template-columns: minmax(0, 1fr) 150px auto auto; align-items: end; gap: 14px; background: #f7f9fb; border: 1px solid #dce2e9; border-radius: 8px; padding: 18px; margin-bottom: 24px; }.exports h3 { margin-bottom: 5px; }.exports p { margin: 0; color: #576678; font-size: 13px; }.export-link { display: inline-flex; justify-content: center; align-items: center; min-height: 40px; border: 1px solid #b9c4d2; border-radius: 5px; padding: 9px 13px; text-decoration: none; white-space: nowrap; }
.filter-heading, .filter-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }.filter-heading { margin-bottom: 0; }.filter-status { color: #576678; font-size: 13px; margin: 4px 0 0; }.filter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 18px 0 16px; }.search-field { grid-column: span 2; }
label { display: block; font-size: 14px; font-weight: 600; }
label span { color: #576678; font-size: 12px; font-weight: 400; }
input, select { display: block; width: 100%; min-width: 0; border: 1px solid #b9c4d2; border-radius: 5px; padding: 10px; margin-top: 7px; font: inherit; font-weight: 400; color: #202c3d; background: #fff; }
input:focus-visible, select:focus-visible, .table-scroll:focus-visible { outline: 3px solid #527ba8; outline-offset: 2px; }
.list-heading { margin: 24px 0 12px; font-size: 14px; color: #576678; }
.table-panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; overflow: hidden; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
th { background: #edf1f5; font-size: 12px; color: #526174; font-weight: 650; white-space: nowrap; }
th, td { padding: 10px 12px; border-bottom: 1px solid #e5e9ee; vertical-align: top; }
td { overflow-wrap: anywhere; min-width: 140px; max-width: 300px; }
tr:last-child td { border-bottom: 0; }
.date-cell { white-space: nowrap; }
.status-badge { display: inline-block; background: #eaf1fc; color: #2a5189; font-size: 11px; font-weight: 700; padding: 4px 7px; border-radius: 4px; }
.interview { background: #f0e9fa; color: #654388; } .closed, .withdrawn, .ghosted { background: #edf0f3; color: #526174; }
.successful { background: #eaf5ee; color: #216344; } .unsuccessful { background: #fcebed; color: #a12c32; } .job_cancelled { background: #fff1de; color: #844d15; }
a { color: #24568b; text-underline-offset: 3px; }
.email-reference { display: block; margin-top: 4px; white-space: pre-wrap; }
.empty { padding: 32px 24px; margin: 0; color: #576678; font-size: 14px; line-height: 1.6; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 900px) { .exports { grid-template-columns: 1fr 150px; }.exports div { grid-column: span 2; } }@media (max-width: 750px) { .filter-grid { grid-template-columns: 1fr 1fr; }.search-field { grid-column: span 2; } }@media (max-width: 600px) { .filter-grid, .exports { grid-template-columns: 1fr; } .exports div { grid-column: span 1; }.search-field { grid-column: span 1; }.filters { padding: 18px; } .page-heading { align-items: flex-start; } }
</style>
