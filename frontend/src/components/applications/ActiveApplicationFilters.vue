<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import Chip from 'primevue/chip'
import type { ApplicationFilters } from '../../api'
import { activeFilterLabels } from '../../applicationFilters'

const props = defineProps<{ filters: ApplicationFilters; loading: boolean }>()
const emit = defineEmits<{ remove: [key: keyof ApplicationFilters]; clear: [] }>()
const active = computed(() => activeFilterLabels(props.filters))
</script>

<template>
  <div v-if="active.length" class="active-filters" aria-label="Active application filters">
    <!-- Keep chips visible until the backend accepts the changed filters. -->
    <Chip v-for="filter in active" :key="filter.key">
      <span>{{ filter.label }}</span>
      <Button type="button" icon="pi pi-times" :aria-label="`Remove ${filter.label}`" severity="secondary" text rounded size="small" :disabled="loading" @click="emit('remove', filter.key)" />
    </Chip>
    <Button type="button" label="Clear all" severity="secondary" text :disabled="loading" @click="emit('clear')" />
  </div>
</template>

<style scoped>
.active-filters { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:12px 0; font-size:12px; }
</style>
