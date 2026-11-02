<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import ActiveApplicationFilters from './components/applications/ActiveApplicationFilters.vue'
import { getDashboard, listApplications, type Application, type ApplicationFilters, type DashboardData } from './api'
import ApplicationFocus from './ApplicationFocus.vue'
import ApplicationTable from './components/applications/ApplicationTable.vue'
import ApplicationSyncControl from './components/applications/ApplicationSyncControl.vue'
import { tablePreferences, updateTablePreferences } from './settings/tablePreferences'
import TablePreferences from './components/settings/TablePreferences.vue'
import ApplicationFilterForm from './ApplicationFilters.vue'
import { activeFilterLabels, appliedFilters, blankFilters } from './applicationFilters'

function selectedId() {
  const match = window.location.hash.match(/^#\/applications\/([^/]+)$/)
  return match ? match[1]! : null
}
const focusedId = ref(selectedId())
function navigate() { focusedId.value = selectedId(); if (!focusedId.value) void refresh() }
const applications = ref<Application[]>([])
const dashboard = ref<DashboardData | null>(null)
const loading = ref(false)
const loadError = ref('')
const filters = reactive<ApplicationFilters>({ ...appliedFilters })
const overdueIds = computed(() => new Set(dashboard.value?.overdue_followups.map(item => item.application.id) ?? []))
const activeFilters = computed(() => activeFilterLabels(appliedFilters))
const hasFilters = computed(() => activeFilters.value.length > 0)
let requestVersion = 0

async function refresh(requestedFilters: ApplicationFilters = { ...appliedFilters }) {
  const version = ++requestVersion
  loading.value = true
  loadError.value = ''
  try {
    const [records, summary] = await Promise.all([listApplications(requestedFilters), getDashboard()])
    if (version !== requestVersion) return
    applications.value = records
    dashboard.value = summary
    Object.assign(appliedFilters, blankFilters(), requestedFilters)
  } catch {
    if (version === requestVersion) loadError.value = t("Unable to load applications. Check that the backend is running, then refresh the list.")
  } finally { if (version === requestVersion) loading.value = false }
}
function applyFilters() { void refresh({ ...filters }) }
function clearFilters() { Object.assign(filters, blankFilters()); void refresh(blankFilters()) }
function removeFilter(key: keyof ApplicationFilters) {
  filters[key] = ''
  void refresh({ ...appliedFilters, [key]: '' })
}
function onInvalidation() { if (!focusedId.value) void refresh() }
onMounted(() => {
  window.addEventListener('hashchange', navigate)
  window.addEventListener('tracker:invalidate', onInvalidation)
  if (!focusedId.value) void refresh()
})
onUnmounted(() => {
  requestVersion++
  window.removeEventListener('hashchange', navigate)
  window.removeEventListener('tracker:invalidate', onInvalidation)
})
</script>

<template>
  <ApplicationFocus v-if="focusedId" :key="focusedId" :id="focusedId" />
  <section v-else aria-labelledby="applications-title">
    <div class="page-heading"><div><h2 id="applications-title">{{ t("All applications") }}</h2></div><Button as="a" href="#/applications/new" :label="t('Add application')" icon="pi pi-plus" /></div>
    <p class="intro">{{ t("Track every role, follow-up, and next step.") }}</p>
    <div class="list-tools"><ApplicationFilterForm :filters="filters" :loading="loading" @apply="applyFilters" @clear="clearFilters" />

    <TablePreferences /><Button v-if="tablePreferences.columns.some(column => !['outcome', 'nextAction'].includes(column))" type="button" severity="secondary" text icon="pi pi-align-justify" :label="t('Simple view')" @click="updateTablePreferences({ columns: ['outcome', 'nextAction'] })" /></div>
    <ActiveApplicationFilters :filters="appliedFilters" :loading="loading" @remove="removeFilter" @clear="clearFilters" />
    <div class="list-heading"><span aria-live="polite">{{ applications.length }} {{ applications.length === 1 ? 'application' : 'applications' }}{{ hasFilters ? t(" matched") : '' }}</span><ApplicationSyncControl @changed="refresh()" /></div>
    <p v-if="loadError" class="at-message error" role="alert">{{ errorText(loadError) }}</p>
    <ApplicationTable :applications="applications" :dashboard="dashboard" :overdue-ids="overdueIds" :loading="loading" :has-filters="hasFilters" :error="Boolean(loadError)" />
  </section>
</template>
<style scoped>
@layer legacy {
.page-heading, .list-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.list-tools { display:flex; flex-wrap:wrap; align-items:flex-start; gap:8px; margin-block:16px; }.list-tools :deep(details) { margin:0; }.list-tools :deep(details[open]) { flex:1 1 100%; }.list-tools :deep(summary) { padding:10px 14px; font-size:13px; }
.list-heading { margin:16px 0 12px; font-size:14px; color:var(--at-text-muted); }
}
</style>
