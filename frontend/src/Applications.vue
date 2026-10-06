<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { getDashboard, listApplications, type Application, type ApplicationFilters } from './api'
import ApplicationFocus from './ApplicationFocus.vue'
import Pagination from './Pagination.vue'
import { jobSourceLabel } from './applicationOptions'
import ApplicationFilterForm from './ApplicationFilters.vue'
import { appliedFilters, blankFilters } from './applicationFilters'

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
const filters = reactive<ApplicationFilters>({ ...appliedFilters })
const overdueIds = ref(new Set<string>())
const page = ref(1)
const pageSize = 10
const hasFilters = computed(() => Object.values(appliedFilters).some(Boolean))
const visibleApplications = computed(() => applications.value.slice((page.value - 1) * pageSize, page.value * pageSize))
function rowTone(application: Application) {
  if (application.status === 'CLOSED') return 'row-closed'
  return overdueIds.value.has(application.id) ? 'row-overdue' : ''
}
function emailReferenceUrl(reference: string | null) {
  if (!reference) return null
  try {
    const url = new URL(reference)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null
  } catch { return null }
}

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    const requestedFilters = { ...filters }
    const [records, dashboard] = await Promise.all([listApplications(requestedFilters), getDashboard()])
    applications.value = records
    overdueIds.value = new Set(dashboard.overdue_followups.map(item => item.application.id))
    Object.assign(appliedFilters, requestedFilters)
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
  <section v-else aria-label="Applications">
    <ApplicationFilterForm :filters="filters" :loading="loading" @apply="refresh" @clear="clearFilters" />

    <div class="list-heading"><span>{{ applications.length }} {{ applications.length === 1 ? 'application' : 'applications' }}{{ hasFilters ? ' matched' : '' }}</span><button type="button" :disabled="loading" @click="refresh">{{ loading ? 'Loading…' : 'Refresh list' }}</button></div>
    <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
    <div class="table-panel" :aria-busy="loading">
      <p v-if="loading && !applications.length" class="empty" role="status">Loading applications…</p>
      <p v-else-if="!applications.length && !loadError" class="empty">{{ hasFilters ? 'No applications match these filters.' : 'No applications yet. Add your first submitted application to get started.' }}</p>
      <div v-else-if="applications.length" class="table-scroll" tabindex="0" role="region" aria-label="Applications table">
        <table>
          <caption class="sr-only">Applications, newest applied date first</caption>
          <thead><tr><th scope="col">Date applied</th><th scope="col">Company</th><th scope="col">Position</th><th scope="col">Status</th><th scope="col">Outcome</th><th scope="col">Source</th></tr></thead>
          <tbody><tr v-for="application in visibleApplications" :key="application.id" :class="rowTone(application)" :aria-label="rowTone(application) === 'row-overdue' ? 'Overdue follow-up' : undefined">
            <td class="date-cell">{{ application.date_applied }}</td><td>{{ application.company }}<small v-if="application.intermediary" class="via">Via {{ application.intermediary }}</small></td><td><a :href="`#/applications/${application.id}`">{{ application.job_title }}</a></td>
            <td><span class="status-badge" :class="application.status.toLowerCase()">{{ application.status }}</span></td>
            <td><span v-if="application.outcome" class="status-badge" :class="application.outcome.toLowerCase()">{{ application.outcome }}</span><span v-else>—</span></td>
            <td class="source-cell"><span>{{ jobSourceLabel(application.source) }}</span><a v-if="application.job_url" :href="application.job_url" target="_blank" rel="noopener noreferrer">posting</a><a v-if="emailReferenceUrl(application.email_reference)" :href="emailReferenceUrl(application.email_reference)!" target="_blank" rel="noopener noreferrer">email ref</a></td>
          </tr></tbody>
        </table>
      </div>
      <Pagination v-model:page="page" :total="applications.length" label="applications" />
    </div>
  </section>
</template>

<style scoped>
.via { display:block; color:#627084; margin-top:4px; }
.list-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:0 0 12px; font-size:14px; color:#576678; }
.table-scroll:focus-visible { outline:3px solid #527ba8; outline-offset:2px; }
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
.source-cell a { display:block; margin-top:4px; }
.row-overdue { background:#fff1f1; box-shadow:inset 3px 0 #b33b42; }
.row-closed { background:#fff1de; box-shadow:inset 3px 0 #b7791f; }
.empty { padding: 32px 24px; margin: 0; color: #576678; font-size: 14px; line-height: 1.6; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
