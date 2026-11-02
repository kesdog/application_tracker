<script setup lang="ts">
import { t, messageText, errorText, intlLocale } from '../../i18n'

import { ref, watch } from 'vue'
import Button from 'primevue/button'
import { getFollowUpAIResults, importFollowUpAIResult, type FollowUpAIResult } from '../../api'
const props = defineProps<{ applicationId: string; followupId: string; revision: number; disabled?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const results = ref<FollowUpAIResult[]>([])
const input = ref('')
const error = ref('')
const busy = ref(false)
let loadVersion = 0
async function load() {
  const version = ++loadVersion
  try { const rows = await getFollowUpAIResults(props.applicationId, props.followupId); if (version === loadVersion) results.value = rows }
  catch { if (version === loadVersion) error.value = t("Unable to load AI results. Refresh and try again.") }
}
async function save() {
  busy.value = true; error.value = ''
  try {
    const value: unknown = JSON.parse(input.value)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(t("Paste one result JSON object from your agent."))
    await importFollowUpAIResult(props.applicationId, props.followupId, value as Record<string, unknown>)
    input.value = ''; await load(); emit('changed')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to import the result. Your text is retained.") }
  finally { busy.value = false }
}
watch(() => [props.applicationId, props.followupId, props.revision], load, { immediate: true })
</script>

<template>
  <details class="ai-results"><summary>{{ t("AI results and mailbox drafts") }}</summary>
    <p>{{ t("Copy AI instructions into your agent. If it cannot report through the tracker tools, paste its result JSON here. A mailbox draft still needs your review and manual sending.") }}</p>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <ul v-if="results.length"><li v-for="result in results" :key="result.operation_id"><strong>{{ result.agent_name }} · {{ messageText(String((result.status.replaceAll('_', ' ')) ?? '')) }}</strong><p>{{ new Date(result.recorded_at).toLocaleString(intlLocale) }} {{ t("· message revision") }} {{ result.accepted_revision }}</p><p v-if="result.draft_reference">{{ t("Draft reference:") }} <code>{{ result.draft_reference }}</code></p><p v-if="result.details">{{ result.details }}</p></li></ul>
    <p v-else>{{ t("No AI results recorded.") }}</p>
    <form @submit.prevent="save"><label>{{ t("Import AI result") }}<textarea v-model="input" rows="6" :aria-label="t('AI result JSON')" :disabled="busy || disabled" :placeholder="t('{\x22operation_id\x22: \x22...\x22, \x22expected_revision\x22: 1, \x22status\x22: \x22revised_message\x22, \x22body\x22: \x22...\x22}')" /></label><Button type="submit" :disabled="busy || disabled || !input.trim()">{{ t("Import result for review") }}</Button></form>
  </details>
</template>

<style scoped>
.ai-results{margin:16px 0}summary{cursor:pointer;font-weight:600}p{overflow-wrap:anywhere}label{display:block;font-weight:600}textarea{display:block;width:100%;box-sizing:border-box;font:inherit;padding:10px;margin:8px 0;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}li{margin:14px 0}li p{margin:5px 0}
</style>
