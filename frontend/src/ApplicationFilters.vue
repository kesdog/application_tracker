<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import type { ApplicationFilters } from './api'
import { jobSources, remotePolicies } from './applicationOptions'
import { contractOptions, outcomeOptions, statusOptions } from './presentation/applicationPresentation'
import DatePicker from './DatePicker.vue'
const props = defineProps<{ filters: ApplicationFilters; loading?: boolean }>()
defineEmits<{ apply: []; clear: [] }>()
const hasFilters = computed(() => Object.values(props.filters).some(Boolean))
</script>
<template>
  <details class="filters"><summary>Filters <span v-if="hasFilters">· Filters selected</span></summary>
    <form aria-label="Application filters" @submit.prevent="$emit('apply')"><fieldset :disabled="loading">
      <div class="filter-grid">
        <label class="search-field">Search<InputText v-model="filters.q" class="at-form-control" type="search" placeholder="Company, title, description…" /></label>
        <div><label for="filter-status">Status</label><Select input-id="filter-status" v-model="filters.status" class="at-form-control" :options="[{ value: '', label: 'Any status' }, ...statusOptions]" option-label="label" option-value="value" :disabled="loading" /></div>
        <div><label for="filter-outcome">Outcome</label><Select input-id="filter-outcome" v-model="filters.outcome" class="at-form-control" :options="[{ value: '', label: 'Any outcome' }, ...outcomeOptions]" option-label="label" option-value="value" :disabled="loading" /></div>
        <label>Company<InputText v-model="filters.company" class="at-form-control" /></label><label>Position<InputText v-model="filters.title" class="at-form-control" /></label><label>Location<InputText v-model="filters.location" class="at-form-control" /></label>
        <div><label for="filter-contract">Contract type</label><Select input-id="filter-contract" v-model="filters.contract_type" class="at-form-control" :options="[{ value: '', label: 'Any contract' }, ...contractOptions]" option-label="label" option-value="value" :disabled="loading" /></div>
        <div><label for="filter-source">Source</label><Select input-id="filter-source" v-model="filters.source" class="at-form-control" :options="[{ value: '', label: 'Any source' }, ...jobSources]" option-label="label" option-value="value" :disabled="loading" /></div>
        <div><label for="filter-remote">Remote policy</label><Select input-id="filter-remote" v-model="filters.remote_policy" class="at-form-control" :options="[{ value: '', label: 'Any policy' }, ...remotePolicies]" option-label="label" option-value="value" :disabled="loading" /></div>
        <label>Document filename<InputText v-model="filters.document_filename" class="at-form-control" placeholder="CV or cover letter filename" /></label>
        <DatePicker v-model="filters.date_from" label="Applied from" :max="filters.date_to || undefined" :disabled="loading" /><DatePicker v-model="filters.date_to" label="Applied to" :min="filters.date_from || undefined" :disabled="loading" />
      </div>
      <div class="filter-actions"><Button label="Apply filters" type="submit" :disabled="loading" /><Button v-if="hasFilters" label="Clear filters" severity="secondary" outlined :disabled="loading" @click="$emit('clear')" /></div>
    </fieldset></form>
  </details>
</template>
<style scoped>
@layer legacy {
.filters { background:var(--at-surface); border:1px solid var(--at-border); border-radius:8px; margin-bottom:16px; }
summary { padding:12px 16px; cursor:pointer; font-size:14px; font-weight:600; }summary span { color:var(--at-text-muted); font-size:12px; font-weight:400; }
form { padding:0 16px 16px; }fieldset { border:0; padding:0; margin:0; min-width:0; }
.filter-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:14px; margin:6px 0 16px; }.search-field { grid-column:span 2; }.filter-actions { display:flex; gap:10px; }label { display:block; font-size:13px; font-weight:600; }
@media (max-width:750px) { .filter-grid { grid-template-columns:1fr 1fr; } }@media (max-width:600px) { .filter-grid { grid-template-columns:1fr; }.search-field { grid-column:span 1; } }
}
</style>
