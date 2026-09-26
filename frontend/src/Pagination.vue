<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ page: number; total: number; pageSize?: number; label?: string }>(), {
  pageSize: 10,
  label: 'records',
})
const emit = defineEmits<{ 'update:page': [page: number] }>()
const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const current = computed(() => Math.min(Math.max(1, props.page), pageCount.value))
const start = computed(() => props.total ? (current.value - 1) * props.pageSize + 1 : 0)
const end = computed(() => Math.min(current.value * props.pageSize, props.total))
</script>

<template>
  <nav v-if="total" class="pagination" :aria-label="`${label} pagination`">
    <span>Showing {{ start }}–{{ end }} of {{ total }}</span>
    <div class="controls">
      <button type="button" :disabled="current === 1" @click="emit('update:page', current - 1)">Previous</button>
      <span>Page {{ current }} of {{ pageCount }}</span>
      <button type="button" :disabled="current === pageCount" @click="emit('update:page', current + 1)">Next</button>
    </div>
  </nav>
</template>

<style scoped>
.pagination { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 14px; border-top:1px solid #e5e9ee; color:#627084; font-size:12px; }
.controls { display:flex; align-items:center; gap:8px; }.controls button { padding:5px 9px; font-size:12px; }
@media (max-width:500px) { .pagination { align-items:flex-start; flex-direction:column; } }
</style>
