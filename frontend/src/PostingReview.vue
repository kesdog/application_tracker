<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { checkPosting, getPostingReview, recordPostingReview, type Application, type PostingReviewPlan } from './api'

const props = defineProps<{ application: Application }>()
const emit = defineEmits<{ changed: [] }>()
const plan = ref<PostingReviewPlan | null>(null)
const busy = ref(false)
const error = ref('')
const copyMessage = ref('')
const showPrompt = ref(false)
const status = ref<Application['posting_status']>('UNKNOWN')
const evidenceUrl = ref('')
const notes = ref('')
const samePosition = ref(false)
const replaceUrl = ref(false)
function localNow() {
  const date = new Date()
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
const checkedAt = ref(localNow())
const label = computed(() => !props.application.posting_last_checked_at ? 'Not checked'
  : props.application.posting_status === 'UNKNOWN' || props.application.posting_check_failures > 0 ? 'Unable to verify'
  : props.application.posting_status === 'LIVE' ? 'Live' : 'Closed')

watch(() => props.application, async (_application, _previous, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  plan.value = null; copyMessage.value = ''; showPrompt.value = false
  try { const nextPlan = await getPostingReview(props.application.id); if (active) plan.value = nextPlan }
  catch (cause) { if (active) error.value = cause instanceof Error ? cause.message : 'Unable to prepare the search.' }
}, { immediate: true })
watch([status, samePosition], () => { if (status.value !== 'LIVE' || !samePosition.value) replaceUrl.value = false })

async function agentSearch() {
  if (!plan.value) return
  try {
    await navigator.clipboard.writeText(plan.value.agent_search_prompt)
    copyMessage.value = 'Search prompt copied. Paste it into your connected agent.'
  } catch {
    showPrompt.value = true
    copyMessage.value = 'Copy the prepared prompt below and paste it into your connected agent.'
  }
}

async function check() {
  busy.value = true; error.value = ''
  try { await checkPosting(props.application.id); emit('changed') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Unable to check the posting.' }
  finally { busy.value = false }
}

async function saveReview() {
  busy.value = true; error.value = ''
  try {
    await recordPostingReview(props.application.id, { status: status.value, evidence_url: evidenceUrl.value,
      notes: notes.value, checked_at: new Date(checkedAt.value).toISOString(), same_position: samePosition.value, replace_job_url: replaceUrl.value })
    emit('changed')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Unable to save the review.' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="posting-panel" aria-labelledby="posting-title">
    <h3 id="posting-title">Job posting</h3>
    <p v-if="application.job_url || application.posting_last_checked_at"><strong>{{ label }}</strong><span v-if="application.posting_last_checked_at"> · {{ new Date(application.posting_last_checked_at).toLocaleString() }} (local time)</span></p>
    <p v-if="application.posting_check_failures > 0 && application.posting_status !== 'UNKNOWN'" class="hint">Last confirmed status: {{ application.posting_status }}. The latest check was inconclusive.</p>
    <div v-if="application.job_url" class="step">
      <h4>Check the saved posting</h4>
      <p class="hint">Checks the URL, then opens the page in a browser if needed.</p>
      <button type="button" :disabled="busy" @click="check">{{ busy ? 'Working…' : 'Check now' }}</button>
      <a :href="application.job_url" target="_blank" rel="noopener noreferrer">Open saved posting ↗</a>
    </div>
    <div class="step">
      <h4>{{ application.job_url ? 'Search for the position' : 'Find the missing job URL' }}</h4>
      <div class="searches"><a v-if="plan" :href="plan.searches[0]?.url" target="_blank" rel="noopener noreferrer">Search manually</a><button type="button" :disabled="!plan" @click="agentSearch">Agent search</button></div>
      <p v-if="copyMessage" class="hint" role="status">{{ copyMessage }}</p>
      <label v-if="showPrompt" class="prepared-prompt">Agent search prompt<textarea :value="plan?.agent_search_prompt" readonly rows="12" @focus="($event.target as HTMLTextAreaElement).select()" /></label>
    </div>
    <details class="step">
      <summary>Record a browser review or update the link</summary>
      <form @submit.prevent="saveReview">
        <fieldset :disabled="busy">
          <label>Conclusion<select v-model="status"><option value="UNKNOWN">Unable to verify</option><option value="LIVE">Live — accepting applications</option><option value="CLOSED">Closed — explicit closure evidence</option></select></label>
          <label>Page checked<input v-model="evidenceUrl" type="url" required maxlength="2048" placeholder="https://…" /></label>
          <label>Checked at (local time)<input v-model="checkedAt" type="datetime-local" required /></label>
          <label>What did you find?<textarea v-model="notes" required minlength="10" maxlength="500" rows="3" placeholder="Describe the matching role and the evidence for your conclusion." /></label>
          <label class="checkbox"><input v-model="samePosition" type="checkbox" />I verified this is the same position and employer.</label>
          <label class="checkbox"><input v-model="replaceUrl" type="checkbox" :disabled="status !== 'LIVE' || !samePosition" />Use this verified live page as the job posting link.</label>
          <button type="submit" :disabled="status !== 'UNKNOWN' && !samePosition">Save review</button>
        </fieldset>
      </form>
    </details>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <details v-if="application.posting_check_reason" class="step"><summary>Last check details</summary>
      <p>{{ application.posting_check_reason }}</p><p v-if="application.posting_check_method || application.posting_http_status !== null" class="hint"><template v-if="application.posting_check_method">Method: {{ application.posting_check_method }}</template><template v-if="application.posting_check_method && application.posting_http_status !== null"> · </template><template v-if="application.posting_http_status !== null">HTTP: {{ application.posting_http_status }}</template></p>
      <a v-if="application.posting_final_url" :href="application.posting_final_url" target="_blank" rel="noopener noreferrer">Last page checked ↗</a>
    </details>
    <p class="hint">Posting availability does not change the status or outcome of your application.</p>
  </section>
</template>

<style scoped>
.posting-panel { padding:24px; border:1px solid #dce2e9; border-radius:10px; background:white; }
h3 { margin:0 0 14px; } h4 { margin:0 0 8px; } .hint { color:#627084; font-size:13px; line-height:1.5; }
.step { border-top:1px solid #e5e9ee; padding:16px 0; } .searches { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
.searches a { display:inline-flex; align-items:center; min-height:36px; padding:9px 13px; border:1px solid #b9c4d2; border-radius:6px; font-size:13px; font-weight:600; text-decoration:none; }
.prepared-prompt { display:block; margin-top:12px; }
a { color:#24568b; overflow-wrap:anywhere; } button + a { margin-left:12px; } summary { cursor:pointer; font-weight:600; }
fieldset { border:0; padding:16px 0 0; display:grid; gap:14px; } label { font-size:14px; font-weight:600; }
input, select, textarea { display:block; width:100%; margin-top:6px; padding:9px; border:1px solid #b9c4d2; border-radius:6px; font:inherit; }
.checkbox { display:flex; align-items:center; gap:8px; font-weight:400; } .checkbox input { width:auto; margin:0; } button { justify-self:start; }
</style>
