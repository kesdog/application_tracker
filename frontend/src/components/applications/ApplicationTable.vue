<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import type { Application, DashboardData } from '../../api'
import { applicationRowClass, contractLabel, remotePolicyMeta, sourceLabel } from '../../presentation/applicationPresentation'
import { nextApplicationAction } from '../../presentation/nextAction'
import { tablePreferences, updateTablePreferences } from '../../settings/tablePreferences'
import AppTag from '../shared/AppTag.vue'
import ApplicationStatusTag from './ApplicationStatusTag.vue'
import ApplicationOutcomeTag from './ApplicationOutcomeTag.vue'
import ApplicationNextAction from './ApplicationNextAction.vue'
import EmailReference from '../../EmailReference.vue'

const props = defineProps<{ applications: Application[]; dashboard: DashboardData | null; overdueIds: Set<string>; loading: boolean; hasFilters: boolean; error: boolean }>()
const first = ref(0)
const columns = computed(() => new Set(tablePreferences.columns))
watch(() => props.applications, () => { first.value = 0 })
watch(() => tablePreferences.pageSize, () => { first.value = 0 })
</script>
<template>
  <div class="table-panel" :aria-busy="loading" :class="`density-${tablePreferences.density}`">
    <DataTable v-model:first="first" :value="applications" data-key="id" paginator :rows="tablePreferences.pageSize" :rows-per-page-options="[10, 20, 50, 100]" :loading="loading" sort-field="date_applied" :sort-order="-1" :row-class="(row: Application) => applicationRowClass(row, overdueIds)" paginator-template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown CurrentPageReport" current-page-report-template="{first}–{last} of {totalRecords}" :table-props="{ 'aria-label': 'Applications' }" :table-style="{ minWidth: '48rem' }" @update:rows="updateTablePreferences({ pageSize: $event })">
      <template #empty><p class="empty" :role="loading ? 'status' : undefined">{{ loading ? 'Loading applications…' : error ? 'Applications could not be loaded. Try refreshing the list.' : hasFilters ? 'No applications match these filters.' : 'No applications yet. Add your first submitted application to get started.' }}</p></template>
      <Column field="date_applied" header="Date applied" sortable><template #body="{ data }"><span class="date-cell">{{ data.date_applied }}</span></template></Column>
      <Column field="company" header="Company" sortable><template #body="{ data }"><strong class="company">{{ data.company }}</strong><small v-if="data.intermediary" class="secondary">Via {{ data.intermediary }}</small></template></Column>
      <Column field="job_title" header="Position" sortable><template #body="{ data }"><a class="position" :href="`#/applications/${data.id}`">{{ data.job_title }}</a><span v-if="overdueIds.has(data.id) && !columns.has('nextAction')" class="secondary">Overdue follow-up</span></template></Column>
      <Column v-if="columns.has('location')" field="location" header="Location" sortable><template #body="{ data }">{{ data.location || '—' }}<small v-if="data.remote_policy" class="secondary">{{ remotePolicyMeta[data.remote_policy]?.label ?? data.remote_policy }}</small></template></Column>
      <Column v-if="columns.has('contract')" header="Contract"><template #body="{ data }"><AppTag v-if="data.contract_type" :label="contractLabel(data.contract_type)" /><span v-else>—</span></template></Column>
      <Column field="status" header="Status" sortable><template #body="{ data }"><ApplicationStatusTag :status="data.status" /></template></Column>
      <Column v-if="columns.has('outcome')" header="Outcome"><template #body="{ data }"><ApplicationOutcomeTag :outcome="data.outcome" /></template></Column>
      <Column v-if="columns.has('nextAction')" header="Next action"><template #body="{ data }"><ApplicationNextAction :action="nextApplicationAction(data.id, dashboard)" /></template></Column>
      <Column v-if="columns.has('source')" header="Source"><template #body="{ data }"><div class="source-cell"><span>{{ sourceLabel(data.source) }}</span><a v-if="data.job_url" :href="data.job_url" target="_blank" rel="noopener noreferrer" :aria-label="`Open posting for ${data.job_title} at ${data.company}`">Posting <i class="pi pi-external-link" aria-hidden="true" /></a><EmailReference v-if="data.email_reference" :reference="data.email_reference" /></div></template></Column>
    </DataTable>
  </div>
</template>
<style scoped>
.table-panel { background:var(--at-surface); border:1px solid var(--at-border); border-radius:8px; overflow:hidden; }
:deep(.p-datatable-table-container) { overflow-x:auto; }
:deep(.p-datatable-thead > tr > th) { white-space:nowrap; font-size:12px; }
:deep(.p-datatable-tbody > tr > td) { vertical-align:top; font-size:13px; min-width:110px; max-width:300px; overflow-wrap:anywhere; }
.density-compact :deep(.p-datatable-tbody > tr > td), .density-compact :deep(.p-datatable-thead > tr > th) { padding:10px 12px; }
.density-comfortable :deep(.p-datatable-tbody > tr > td) { padding:18px 14px; }
:deep(.p-datatable-tbody > tr.row-overdue) { background:color-mix(in srgb, var(--at-overdue) 6%, var(--at-surface)); }
:deep(.row-overdue > td:first-child) { box-shadow:inset 3px 0 var(--at-overdue); }
:deep(.p-datatable-tbody > tr.row-closed) { background:color-mix(in srgb, var(--at-posting-closed) 6%, var(--at-surface)); }
:deep(.row-closed > td:first-child) { box-shadow:inset 3px 0 var(--at-posting-closed); }
.company { font-weight:550; }.secondary { display:block; color:var(--at-text-muted); margin-top:4px; font-size:12px; }.date-cell { white-space:nowrap; }.position { font-weight:600; }
.source-cell :deep(a) { display:block; margin-top:4px; font-size:12px; }.source-cell i { font-size:10px; }
.empty { padding:24px 12px; margin:0; color:var(--at-text-muted); line-height:1.6; }
</style>
