<script setup lang="ts">
import { computed } from 'vue'
import type { ApplicationFilters } from './api'
import { jobSources, remotePolicies } from './applicationOptions'
import DatePicker from './DatePicker.vue'

const props = defineProps<{ filters: ApplicationFilters; loading?: boolean }>()
defineEmits<{ apply: []; clear: [] }>()
const hasFilters = computed(() => Object.values(props.filters).some(Boolean))
const statuses = ['', 'SUBMITTED', 'INTERVIEW', 'CLOSED'] as const
const outcomes = ['', 'SUCCESSFUL', 'UNSUCCESSFUL', 'WITHDRAWN', 'JOB_CANCELLED', 'GHOSTED'] as const
const contracts = [
  { value: 'CDI', label: 'Full time (CDI)' },
  { value: 'CDD', label: 'Fixed term (CDD)' },
  { value: 'PART_TIME', label: 'Part time (Temps partiel)' },
  { value: 'APPRENTICESHIP_INTERNSHIP', label: 'Apprenticeship / Internship (Alternance / Stage)' },
]
</script>

<template>
  <details class="filters">
    <summary>Filters <span v-if="hasFilters" class="filter-status">· Filters selected</span></summary>
    <form aria-label="Application filters" @submit.prevent="$emit('apply')">
      <div class="filter-grid">
        <label class="search-field">Search<input v-model="filters.q" type="search" placeholder="Company, title, description…" /></label>
        <label>Status<select v-model="filters.status"><option v-for="status in statuses" :key="status" :value="status">{{ status || 'Any status' }}</option></select></label>
        <label>Outcome<select v-model="filters.outcome"><option v-for="outcome in outcomes" :key="outcome" :value="outcome">{{ outcome || 'Any outcome' }}</option></select></label>
        <label>Company<input v-model="filters.company" /></label><label>Position<input v-model="filters.title" /></label><label>Location<input v-model="filters.location" /></label>
        <label>Contract type<select v-model="filters.contract_type"><option value="">Any contract</option><option v-for="contract in contracts" :key="contract.value" :value="contract.value">{{ contract.label }}</option></select></label>
        <label>Source<select v-model="filters.source"><option value="">Any source</option><option v-for="option in jobSources" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <label>Remote policy<select v-model="filters.remote_policy"><option value="">Any policy</option><option v-for="option in remotePolicies" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <label>Document filename<input v-model="filters.document_filename" placeholder="CV or cover letter filename" /></label>
        <DatePicker v-model="filters.date_from" label="Applied from" :max="filters.date_to || undefined" /><DatePicker v-model="filters.date_to" label="Applied to" :min="filters.date_from || undefined" />
      </div>
      <div class="filter-actions"><button class="primary" type="submit" :disabled="loading">Apply filters</button><button v-if="hasFilters" type="button" :disabled="loading" @click="$emit('clear')">Clear filters</button></div>
    </form>
  </details>
</template>

<style scoped>
.filters { background:#fff; border:1px solid #dce2e9; border-radius:8px; margin-bottom:16px; }
summary { padding:12px 16px; cursor:pointer; font-size:14px; font-weight:600; color:#293e58; }
summary:focus-visible { outline:3px solid #527ba8; outline-offset:2px; }
form { padding:0 16px 16px; }
.filter-status { color:#576678; font-size:12px; font-weight:400; }
.filter-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:14px; margin:6px 0 16px; }
.search-field { grid-column:span 2; }
.filter-actions { display:flex; gap:10px; }
.primary { background:#263e5c; border-color:#263e5c; color:#fff; }
label { display:block; font-size:14px; font-weight:600; }
input, select { display:block; width:100%; min-width:0; border:1px solid #b9c4d2; border-radius:5px; padding:10px; margin-top:7px; font:inherit; font-weight:400; color:#202c3d; background:#fff; }
input:focus-visible, select:focus-visible { outline:3px solid #527ba8; outline-offset:2px; }
@media (max-width:750px) { .filter-grid { grid-template-columns:1fr 1fr; } }
@media (max-width:600px) { .filter-grid { grid-template-columns:1fr; }.search-field { grid-column:span 1; } }
</style>
