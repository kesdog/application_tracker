<script setup lang="ts">
import { computed } from 'vue'
import { emailReferenceUrl } from './emailReference'
const props = withDefaults(defineProps<{ reference: string | null; label?: string }>(), { label: 'email ref' })
const url = computed(() => emailReferenceUrl(props.reference))
</script>

<template>
  <a v-if="url" :href="url" :title="reference ?? undefined" target="_blank" rel="noopener noreferrer">{{ label }}</a>
  <span v-else-if="reference">{{ reference }}</span>
</template>

<style scoped>
@layer legacy {
a { color:var(--at-link); text-underline-offset:3px; overflow-wrap:anywhere; }
}
</style>
