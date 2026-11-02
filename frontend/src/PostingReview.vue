<script setup lang="ts">
import { t, messageText, errorText, intlLocale } from './i18n'

import Select from 'primevue/select'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import DateTimeField from './components/shared/DateTimeField.vue'
import InputText from 'primevue/inputtext'
import { computed, ref, watch } from 'vue'
import { checkPosting, getPostingReview, recordPostingReview, type Application, type PostingReviewPlan } from './api'

const props = defineProps<{ application: Application; embedded?: boolean }>()
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
const label = computed(() => !props.application.posting_last_checked_at ? t("Not checked")
  : props.application.posting_status === 'UNKNOWN' || props.application.posting_check_failures > 0 ? t("Unable to verify")
  : props.application.posting_status === 'LIVE' ? t("Live") : t("Closed"))

watch(() => props.application, async (_application, _previous, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  plan.value = null; copyMessage.value = ''; showPrompt.value = false
  try { const nextPlan = await getPostingReview(props.application.id); if (active) plan.value = nextPlan }
  catch (cause) { if (active) error.value = cause instanceof Error ? cause.message : t("Unable to prepare the search.") }
}, { immediate: true })
watch([status, samePosition], () => { if (status.value !== 'LIVE' || !samePosition.value) replaceUrl.value = false })

async function agentSearch() {
  if (!plan.value) return
  try {
    await navigator.clipboard.writeText(plan.value.agent_search_prompt)
    copyMessage.value = t("Search prompt copied. Paste it into your connected agent.")
  } catch {
    showPrompt.value = true
    copyMessage.value = t("Copy the prepared prompt below and paste it into your connected agent.")
  }
}

async function check() {
  busy.value = true; error.value = ''
  try { await checkPosting(props.application.id); emit('changed') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : t("Unable to check the posting.") }
  finally { busy.value = false }
}

async function saveReview() {
  busy.value = true; error.value = ''
  try {
    await recordPostingReview(props.application.id, { status: status.value, evidence_url: evidenceUrl.value,
      notes: notes.value, checked_at: new Date(checkedAt.value).toISOString(), same_position: samePosition.value, replace_job_url: replaceUrl.value })
    emit('changed')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : t("Unable to save the review.") }
  finally { busy.value = false }
}
</script>

<template>
  <section class="posting-panel" :class="{ embedded }" :aria-label="t('Posting checks and search')">
    <h3 v-if="!embedded">{{ t("Job posting") }}</h3>
    <p v-if="(!embedded && application.job_url) || application.posting_last_checked_at"><strong v-if="!embedded">{{ messageText(String((label) ?? '')) }}</strong><span v-if="application.posting_last_checked_at">{{ embedded ? t("Last checked ") : ' · ' }}{{ new Date(application.posting_last_checked_at).toLocaleString(intlLocale) }} {{ t("(local time)") }}</span></p>
    <p v-if="application.posting_check_failures > 0 && application.posting_status !== 'UNKNOWN'" class="hint">{{ t("Last confirmed status:") }} {{ application.posting_status }}{{ t(". The latest check was inconclusive.") }}</p>
    <div v-if="application.job_url" class="step">
      <h4>{{ t("Check the saved posting") }}</h4>
      <p class="hint">{{ t("Checks the URL, then opens the page in a browser if needed.") }}</p>
      <Button type="button" :disabled="busy" @click="check">{{ busy ? t("Working…") : t("Check now") }}</Button>
      <a :href="application.job_url" target="_blank" rel="noopener noreferrer">{{ t("Open saved posting ↗") }}</a>
    </div>
    <div class="step">
      <h4>{{ application.job_url ? t("Search for the position") : t("Find the missing job URL") }}</h4>
      <div class="searches"><a v-if="plan" :href="plan.searches[0]?.url" target="_blank" rel="noopener noreferrer">{{ t("Search manually") }}</a><Button type="button" :disabled="!plan" @click="agentSearch">{{ t("Agent search") }}</Button></div>
      <p v-if="copyMessage" class="hint" role="status">{{ copyMessage }}</p>
      <label v-if="showPrompt" class="prepared-prompt">{{ t("Agent search prompt") }}<Textarea class="at-form-control" :value="plan?.agent_search_prompt" readonly rows="12" @focus="($event.target as HTMLTextAreaElement).select()"></Textarea></label>
    </div>
    <details class="step">
      <summary>{{ t("Record a browser review or update the link") }}</summary>
      <form @submit.prevent="saveReview">
        <fieldset :disabled="busy">
          <label>{{ t("Conclusion") }}<Select class="at-form-control" :aria-label="t('Conclusion')" v-model="status" :disabled="busy" :options="[{ value: 'UNKNOWN', get label() { return t('Unable to verify') } }, { value: 'LIVE', get label() { return t('Live — accepting applications') } }, { value: 'CLOSED', get label() { return t('Closed — explicit closure evidence') } }]" option-label="label" option-value="value" option-disabled="disabled" /></label>
          <label>{{ t("Page checked") }}<InputText class="at-form-control" v-model="evidenceUrl" type="url" required maxlength="2048" :placeholder="t('https://…')" /></label>
          <DateTimeField v-model="checkedAt" :label="t('Checked at (local time)')" :disabled="busy" required />
          <label>{{ t("What did you find?") }}<Textarea class="at-form-control" v-model="notes" required minlength="10" maxlength="500" rows="3" :placeholder="t('Describe the matching role and the evidence for your conclusion.')"></Textarea></label>
          <label class="checkbox"><input v-model="samePosition" type="checkbox" />{{ t("I verified this is the same position and employer.") }}</label>
          <label class="checkbox"><input v-model="replaceUrl" type="checkbox" :disabled="status !== 'LIVE' || !samePosition" />{{ t("Use this verified live page as the job posting link.") }}</label>
          <Button type="submit" :disabled="status !== 'UNKNOWN' && !samePosition">{{ t("Save review") }}</Button>
        </fieldset>
      </form>
    </details>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <details v-if="application.posting_check_reason" class="step"><summary>{{ t("Last check details") }}</summary>
      <p>{{ application.posting_check_reason }}</p><p v-if="application.posting_check_method || application.posting_http_status !== null" class="hint"><template v-if="application.posting_check_method">{{ t("Method:") }} {{ application.posting_check_method }}</template><template v-if="application.posting_check_method && application.posting_http_status !== null"> · </template><template v-if="application.posting_http_status !== null">{{ t("HTTP:") }} {{ application.posting_http_status }}</template></p>
      <a v-if="application.posting_final_url" :href="application.posting_final_url" target="_blank" rel="noopener noreferrer">{{ t("Last page checked ↗") }}</a>
    </details>
    <p class="hint">{{ t("Posting availability does not change the status or outcome of your application.") }}</p>
  </section>
</template>

<style scoped>
.posting-panel.embedded { padding:0 20px 20px; border:0; border-radius:0; background:transparent; }
@layer legacy {
.posting-panel { padding:24px; border:1px solid var(--at-border); border-radius:10px; background:var(--at-surface); }
h3 { margin:0 0 14px; } h4 { margin:0 0 8px; } .hint { color:var(--at-text-muted); font-size:13px; line-height:1.5; }
.step { border-top:1px solid var(--at-border); padding:16px 0; } .searches { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
.searches a { display:inline-flex; align-items:center; min-height:36px; padding:9px 13px; border:1px solid var(--at-border); border-radius:6px; font-size:13px; font-weight:600; text-decoration:none; }
.prepared-prompt { display:block; margin-top:12px; }
a { color:var(--at-link); overflow-wrap:anywhere; } button + a { margin-left:12px; } summary { cursor:pointer; font-weight:600; }
fieldset { border:0; padding:16px 0 0; display:grid; gap:14px; } label { font-size:14px; font-weight:600; }
input, select, textarea { display:block; width:100%; margin-top:6px; padding:9px; border:1px solid var(--at-border); border-radius:6px; font:inherit; }
.checkbox { display:flex; align-items:center; gap:8px; font-weight:400; } .checkbox input { width:auto; margin:0; } button { justify-self:start; }
}
</style>
