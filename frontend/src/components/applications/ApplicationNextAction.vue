<script setup lang="ts">
import { computed } from 'vue'
import type { NextAction } from '../../presentation/nextAction'
import { appearanceVariable } from '../../settings/applyAppearance'
import { dateTimeText, relativeDateText } from '../../dateText'
const props = defineProps<{ action: NextAction | null }>()
const color = computed(() => `var(${appearanceVariable(props.action?.tone === 'neutral' ? 'textMuted' : props.action?.tone ?? 'textMuted')})`)
</script>
<template>
  <div v-if="action" class="next-action" :title="`${action.title}${action.dueAt ? ' · ' + dateTimeText(action.dueAt) : ''}`">
    <strong><i :class="action.icon" aria-hidden="true" /> {{ action.label }}</strong>
    <small v-if="action.dueAt">{{ relativeDateText(action.dueAt) }}</small>
  </div><span v-else aria-label="No upcoming action">—</span>
</template>
<style scoped>
.next-action { border-left:2px solid v-bind(color); padding-left:8px; min-width:150px; }.next-action strong { font-size:12px; font-weight:600; }.next-action small { display:block; color:var(--at-text-muted); margin-top:4px; font-size:12px; }
</style>
