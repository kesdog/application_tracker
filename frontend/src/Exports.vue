<script setup lang="ts">
import Select from 'primevue/select'
import { computed, reactive, ref } from 'vue'
import { applicationExportUrl, type ApplicationFilters } from './api'
import ApplicationFilterForm from './ApplicationFilters.vue'
import { appliedFilters, blankFilters } from './applicationFilters'

const format = ref<'csv' | 'xlsx'>('csv')
const filters = reactive<ApplicationFilters>({ ...appliedFilters })
const selectedFilters = ref<ApplicationFilters>({ ...appliedFilters })
const hasFilters = computed(() => Object.values(selectedFilters.value).some(Boolean))
const allUrl = computed(() => applicationExportUrl(format.value))
const filteredUrl = computed(() => applicationExportUrl(format.value, selectedFilters.value))
function applyFilters() { selectedFilters.value = { ...filters } }
function clearFilters() { Object.assign(filters, blankFilters()); applyFilters() }
</script>

<template>
  <section aria-labelledby="export-title">
    <h2 id="export-title">Export applications</h2>
    <p class="intro">Download CSV or Excel files. Filters from the applications list are carried over here.</p>
    <ApplicationFilterForm :filters="filters" @apply="applyFilters" @clear="clearFilters" />
    <div class="export-panel">
      <label>Format<Select class="at-form-control" aria-label="Format" v-model="format" :options="[{ value: 'csv', label: 'CSV' }, { value: 'xlsx', label: 'Excel (XLSX)' }]" option-label="label" option-value="value" option-disabled="disabled" /></label>
      <a :href="allUrl" :download="`applications.${format}`">Export all applications</a>
      <a v-if="hasFilters" class="primary" :href="filteredUrl" :download="`applications.${format}`">Export filtered applications</a>
    </div>
  </section>
</template>

<style scoped>
@layer legacy {
.export-panel { display:flex; align-items:flex-end; flex-wrap:wrap; gap:14px; padding:20px; background:var(--at-surface); border:1px solid var(--at-border); border-radius:8px; }
label { font-size:14px; font-weight:600; }
select { display:block; margin-top:7px; padding:10px; border:1px solid var(--at-border); border-radius:5px; background:var(--at-surface); color:var(--at-text); font:inherit; }
a { display:inline-flex; align-items:center; min-height:40px; padding:9px 13px; border:1px solid var(--at-border); border-radius:6px; text-decoration:none; color:var(--at-link); font-size:14px; }
.primary { background:var(--at-primary); border-color:var(--at-primary); color:var(--at-primary-contrast); }
}
</style>
