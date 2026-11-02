<script setup lang="ts">
import { t, messageText } from '../../i18n'

import { computed } from 'vue'
const props = defineProps<{ count?: number }>()
const label = computed(() => t("{p0} completed follow-up{p1}", { p0: props.count, p1: props.count === 1 ? '' : 's' }))
</script>
<template>
  <span v-if="count && count > 0" class="completed-followups" :aria-label="messageText(String((label) ?? ''))" :title="messageText(String((label) ?? ''))">
    <i class="pi pi-check" aria-hidden="true" /><span aria-hidden="true">{{ count }}</span>
  </span>
</template>
<style scoped>
.completed-followups { display:inline-flex; align-items:center; gap:5px; vertical-align:middle; white-space:nowrap; margin-left:6px; padding:3px 6px; border-radius:12px; background:#e0f2fe; color:#075985; font-size:12px; font-weight:650; }
.completed-followups i { display:grid; place-items:center; width:17px; height:17px; border-radius:50%; background:#075985; color:#7dd3fc; font-size:10px; }
:global([data-theme="dark"] .completed-followups) { background:#123b58; color:#bae6fd; }
</style>
