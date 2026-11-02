<script setup lang="ts">
import { t, messageText, errorText, intlLocale } from '../../i18n'

import { computed, onMounted, onUnmounted, ref, useId } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import { getApplicationSync, startApplicationSync, type ApplicationSyncStatus } from '../../api'

const emit = defineEmits<{ changed: [] }>()
const result = ref<ApplicationSyncStatus | null>(null)
const starting = ref(false)
const error = ref('')
const initialDialog = ref(false)
const lookbackMonths = ref<number | null>(3)
const choiceAccount = ref<string | null>(null)
const id = useId()
const busy = computed(() => starting.value || result.value?.state === 'RUNNING')
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let version = 0
function accept(value: ApplicationSyncStatus, initiated = false) {
  const wasRunning = result.value?.state === 'RUNNING'
  result.value = value
  if (value.state === 'RUNNING') timer = setTimeout(() => void load(), 1000)
  else if ((wasRunning || initiated) && value.state !== 'IDLE') emit('changed')
}
async function load() {
  const current = ++version
  try {
    const value = await getApplicationSync()
    if (disposed || current !== version) return
    error.value = ''
    accept(value)
  } catch {
    if (disposed || current !== version) return
    error.value = t("Could not read sync progress. Your saved applications are kept.")
    if (result.value?.state === 'RUNNING') timer = setTimeout(() => void load(), 2000)
  }
}
async function sync(months?: number | null) {
  if (busy.value) return
  clearTimeout(timer)
  const current = ++version
  starting.value = true; error.value = ''
  try {
    // Refresh the selected account and saved scope before making a first-run choice.
    const status = await getApplicationSync()
    if (disposed || current !== version) return
    if (status.state === 'RUNNING') { accept(status); return }
    if (status.initial_scan_required && (months === undefined || choiceAccount.value !== (status.gmail_account ?? null))) {
      result.value = status; choiceAccount.value = status.gmail_account ?? null
      lookbackMonths.value = 3; initialDialog.value = true; return
    }
    if (months !== undefined && (months === null || !Number.isInteger(months) || months < 1 || months > 120)) {
      error.value = t("Choose a whole number from 1 to 120 months."); return
    }
    const value = await startApplicationSync(months === undefined ? undefined : { lookback_months: months! })
    initialDialog.value = false
    if (!disposed && current === version) accept(value, true)
  } catch (reason) {
    if (!disposed && current === version) error.value = reason instanceof Error ? reason.message : t("Unable to start sync. Try again.")
  } finally { if (!disposed && current === version) starting.value = false }
}
onMounted(() => void load())
onUnmounted(() => { disposed = true; version++; clearTimeout(timer) })
</script>
<template>
  <div class="application-sync" :aria-busy="busy">
    <Button type="button" severity="secondary" outlined :disabled="busy" @click="sync()"><i :class="busy ? 'pi pi-spinner pi-spin' : 'pi pi-sync'" aria-hidden="true" />{{ busy ? t("Syncing…") : result?.limit_reached ? t("Continue sync") : t("Sync applications") }}</Button>
    <p v-if="busy" role="status">{{ messageText(String((result?.phase === 'DRIVE' ? t("Synchronizing tracker records with Drive…") : t("Checking Gmail for new applications and updates… {p0}{p1} new emails checked.", { p0: result?.checked ?? 0, p1: result?.mail_limit ? ` of ${result.mail_limit}` : '' })) ?? '')) }}</p>
    <p v-else-if="result && result.state !== 'IDLE'" role="status">{{ result.created }} {{ t("new ·") }} {{ result.updated }} {{ t("updated applications ·") }} {{ result.checked }} {{ t("emails checked.") }} {{ result.drive === 'COMPLETED' ? t("Drive synchronized.") : t("Drive sync needs attention.") }}</p>
    <p v-if="result?.limit_reached" role="status">{{ t("Reached the") }} {{ result.mail_limit }}{{ t("-email limit. Saved changes are kept. Continue sync to check the remaining mail; previously checked emails do not count again.") }}</p>
    <p v-if="result?.gmail_checked_through">{{ t("Gmail checked through") }} {{ new Date(result.gmail_checked_through).toLocaleString(intlLocale) }}. {{ result.limit_reached ? t("Remaining mail has not been marked as checked.") : t("Future syncs check newer mail.") }}</p>
    <p v-if="result?.gmail_scan_from">{{ t("Initial mail scan starts from") }} {{ new Date(result.gmail_scan_from).toLocaleDateString(intlLocale) }}.</p>
    <a href="#/settings?tab=connections">{{ t("Mail scan limit & connection settings") }}</a>
    <p v-if="error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <template v-if="!busy && result">
      <p v-for="warning in result.warnings" :key="warning" class="warning">{{ warning }}</p>
      <details v-if="result.review_count"><summary>{{ result.review_count }} {{ result.review_count === 1 ? t("email needs") : t("emails need") }} {{ t("review") }}</summary><p><a href="#/settings?tab=data">{{ t("Resolve emails in Settings → Data & recovery") }}</a></p><ul><li v-for="review in result.reviews ?? []" :key="review.message_id"><a :href="review.url" target="_blank" rel="noopener noreferrer">{{ review.subject }}</a><p>{{ messageText(String((review.reason) ?? '')) }}</p></li></ul><p v-if="result.review_count > (result.reviews?.length ?? 0)">{{ t("Showing the 20 most recent emails needing review.") }}</p></details>
    </template>
  </div>
  <Dialog v-model:visible="initialDialog" modal :header="t('Choose your first mail scan')" :draggable="false" :block-scroll="true" :style="{ width: '30rem', maxWidth: '95vw' }">
    <form class="first-scan-form" @submit.prevent="sync(lookbackMonths)">
      <p v-if="choiceAccount">{{ t("For") }} {{ choiceAccount }}</p>
      <label :for="`${id}-months`">{{ t("How many months back should we check?") }}</label>
      <InputNumber v-model="lookbackMonths" :input-id="`${id}-months`" :min="1" :max="120" :max-fraction-digits="0" :use-grouping="false" :disabled="busy" :pt="{ pcInputText: { root: { 'aria-describedby': `${id}-months-help` } } }" />
      <p :id="`${id}-months-help`">{{ t("Default: 3 months. Choose 1–120. We will check application-related emails from that date onward. Your starting date stays fixed if more than one batch is needed.") }}</p>
      <p>{{ t("Later syncs check newer mail. Nothing is sent.") }}</p>
      <p v-if="error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
      <div class="first-scan-actions"><Button type="button" severity="secondary" :disabled="busy" @click="initialDialog = false">{{ t("Cancel") }}</Button><Button type="submit" :disabled="busy">{{ t("Start mail scan") }}</Button></div>
    </form>
  </Dialog>
</template>
<style scoped>
.application-sync { display:flex; flex-direction:column; align-items:flex-end; gap:8px; max-width:620px; min-width:0; }
p { margin:0; font-size:13px; color:var(--at-text-muted); line-height:1.5; }a { font-size:13px; }details { width:100%; }summary { cursor:pointer; font-size:13px; font-weight:600; }ul { padding-left:20px; }li { margin:12px 0; overflow-wrap:anywhere; }
.warning, [role=alert] { color:var(--at-text); border-left:3px solid var(--at-due-soon); padding-left:10px; }
.first-scan-form { display:flex; flex-direction:column; gap:12px; min-width:0; }.first-scan-form p { overflow-wrap:anywhere; }.first-scan-form :deep(.p-inputnumber), .first-scan-form :deep(input) { width:100%; min-width:0; box-sizing:border-box; }
.first-scan-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:8px; }label { display:block; font-weight:600; }
@media(max-width:650px) { .application-sync { align-items:flex-start; width:100%; } }
</style>
