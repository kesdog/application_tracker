<script setup lang="ts">
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import Button from 'primevue/button'
import { optionalColumns, resetTablePreferences, tablePreferences, tableSaveError, updateTablePreferences, type OptionalColumn } from '../../settings/tablePreferences'
</script>
<template>
  <details class="table-preferences"><summary>Table preferences</summary>
    <div class="preferences-controls">
      <div><label for="table-columns">Optional columns</label><MultiSelect input-id="table-columns" :model-value="[...tablePreferences.columns]" :options="[...optionalColumns]" option-label="label" option-value="value" placeholder="Core columns only" :max-selected-labels="2" selected-items-label="{0} optional columns" @update:model-value="updateTablePreferences({ columns: $event as OptionalColumn[] })" /></div>
      <div><label for="table-density">Row density</label><Select input-id="table-density" :model-value="tablePreferences.density" :options="[{ value: 'compact', label: 'Compact' }, { value: 'comfortable', label: 'Comfortable' }]" option-label="label" option-value="value" @update:model-value="updateTablePreferences({ density: $event })" /></div>
      <div><label for="table-page-size">Default page size</label><Select input-id="table-page-size" :model-value="tablePreferences.pageSize" :options="[10, 20, 50, 100]" @update:model-value="updateTablePreferences({ pageSize: $event })" /></div>
      <Button severity="secondary" outlined label="Reset table" @click="resetTablePreferences" />
    </div><p v-if="tableSaveError" class="at-message warning" role="status">{{ tableSaveError }}</p>
  </details>
</template>
<style scoped>
.table-preferences { margin:12px 0; background:var(--at-surface); border:1px solid var(--at-border); border-radius:8px; }summary { cursor:pointer; font-size:13px; padding:12px 16px; font-weight:600; }.preferences-controls { display:flex; flex-wrap:wrap; gap:16px; padding:0 16px 16px; align-items:flex-end; }label { display:block; font-size:12px; margin-bottom:6px; }.preferences-controls > div:first-child { min-width:230px; }
</style>
