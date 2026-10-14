<script setup lang="ts">
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
  catch { if (version === loadVersion) error.value = 'Unable to load AI results. Refresh and try again.' }
}
async function save() {
  busy.value = true; error.value = ''
  try {
    const value: unknown = JSON.parse(input.value)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Paste one result JSON object from your agent.')
    await importFollowUpAIResult(props.applicationId, props.followupId, value as Record<string, unknown>)
    input.value = ''; await load(); emit('changed')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to import the result. Your text is retained.' }
  finally { busy.value = false }
}
watch(() => [props.applicationId, props.followupId, props.revision], load, { immediate: true })
</script>

<template>
  <details class="ai-results"><summary>AI results and mailbox drafts</summary>
    <p>Copy AI instructions into your agent. If it cannot report through the tracker tools, paste its result JSON here. A mailbox draft still needs your review and manual sending.</p>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p>
    <ul v-if="results.length"><li v-for="result in results" :key="result.operation_id"><strong>{{ result.agent_name }} · {{ result.status.replaceAll('_', ' ') }}</strong><p>{{ new Date(result.recorded_at).toLocaleString() }} · message revision {{ result.accepted_revision }}</p><p v-if="result.draft_reference">Draft reference: <code>{{ result.draft_reference }}</code></p><p v-if="result.details">{{ result.details }}</p></li></ul>
    <p v-else>No AI results recorded.</p>
    <form @submit.prevent="save"><label>Import AI result<textarea v-model="input" rows="6" aria-label="AI result JSON" :disabled="busy || disabled" placeholder='{"operation_id": "...", "expected_revision": 1, "status": "revised_message", "body": "..."}' /></label><Button type="submit" :disabled="busy || disabled || !input.trim()">Import result for review</Button></form>
  </details>
</template>

<style scoped>
.ai-results{margin:16px 0}summary{cursor:pointer;font-weight:600}p{overflow-wrap:anywhere}label{display:block;font-weight:600}textarea{display:block;width:100%;box-sizing:border-box;font:inherit;padding:10px;margin:8px 0;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}li{margin:14px 0}li p{margin:5px 0}
</style>
