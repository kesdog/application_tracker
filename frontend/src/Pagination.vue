<script setup lang="ts">
import { computed } from 'vue'
import Paginator from 'primevue/paginator'

const props = withDefaults(defineProps<{ page: number; total: number; pageSize?: number; label?: string }>(), {
  pageSize: 10,
  label: 'records',
})
const emit = defineEmits<{ 'update:page': [page: number] }>()
const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const current = computed(() => Math.min(Math.max(1, props.page), pageCount.value))
</script>

<template>
  <nav v-if="total" class="pagination" :aria-label="`${label} pagination`">
    <Paginator :first="(current - 1) * pageSize" :rows="pageSize" :total-records="total" template="PrevPageLink CurrentPageReport NextPageLink" current-page-report-template="{first}–{last} of {totalRecords}" @page="emit('update:page', $event.page + 1)" />
  </nav>
</template>

<style scoped>
@layer legacy {
.pagination { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 14px; border-top:1px solid var(--at-border); color:var(--at-text-muted); font-size:12px; }
.controls { display:flex; align-items:center; gap:8px; }.controls button { padding:5px 9px; font-size:12px; }
@media (max-width:500px) { .pagination { align-items:flex-start; flex-direction:column; } }
}
</style>
