<script setup lang="ts">
import { t, messageText, errorText, intlLocale } from './i18n'

import PageTabs from './components/shared/PageTabs.vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import Pagination from './Pagination.vue'
import AppTag from './components/shared/AppTag.vue'
import FollowUpEditor from './FollowUpEditor.vue'
import BusyIndicator from './components/shared/BusyIndicator.vue'
import FollowUpTarget from './components/followups/FollowUpTarget.vue'
import { followupTargetStatus } from './presentation/followupTargets'
import { fetchMissingRecipients, getRecipientQueue, pauseRecipientQueue, resumeRecipientQueue, pauseRecipientSearch, prioritizeRecipientSearch, type RecipientQueue } from './api'
import { getOutcomeReviews, type OutcomeReviewPage } from './api'
import { getFollowUps, getWork, getApplication, getFollowUpNotices, readFollowUpNotice, type FollowUpNotice, type FollowUpPage, type FollowUp, type Application } from './api'
import { followupStatusMeta, urgencyMeta } from './presentation/taskPresentation'
const data = ref<FollowUpPage | null>(null)
const page = ref(1)
const status = ref('')
const due = ref('')
const q = ref('')
const archived = ref(false)
const paused = ref('')
const recipient = ref('')
const recipientQueue = ref<RecipientQueue | null>(null)
const queuing = ref(false)
const queuedNotice = ref('')
let recipientVersion = 0
let recipientTimer: ReturnType<typeof setInterval> | undefined
async function loadRecipients() {
  const version = ++recipientVersion
  try { const result = await getRecipientQueue(); if (version === recipientVersion) recipientQueue.value = result }
  catch { if (version === recipientVersion) error.value = t("Unable to load recipient search status. Refresh and try again.") }
}
async function queueMissing() {
  queuing.value = true; error.value = ''
  try { const result = await fetchMissingRecipients(); queuedNotice.value = t("{p0} recipient searches queued. Up to five run at once.", { p0: result.queued }); await loadRecipients() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to queue recipient searches.") }
  finally { queuing.value = false }
}
async function controlRecipients(action: () => Promise<unknown>) {
  queuing.value = true; error.value = ''
  try { await action(); await loadRecipients() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t('Unable to change recipient search priority.') }
  finally { queuing.value = false }
}
const selected = ref<{ item: FollowUp; application: Application } | null>(null)
const busy = ref(false)
const error = ref('')
const count = computed(() => data.value?.total ?? 0)
const notices = ref<FollowUpNotice[]>([])
const reviews = ref<OutcomeReviewPage | null>(null)
const reviewPage = ref(1)
let reviewVersion = 0
async function loadReviews() {
  const version = ++reviewVersion
  try { const result = await getOutcomeReviews(reviewPage.value); if (version === reviewVersion) { reviews.value = result; const last = Math.max(1, Math.ceil(result.total / 20)); if (reviewPage.value > last) reviewPage.value = last } }
  catch { if (version === reviewVersion) error.value = t("Unable to load outcome reviews. Refresh and try again.") }
}
let requestVersion = 0
let routeVersion = 0
let noticeTimer: ReturnType<typeof setInterval> | undefined
async function loadNotices() {
  void loadReviews()
  try { notices.value = await getFollowUpNotices() } catch { /* Queue remains usable if notices are unavailable. */ }
}
async function dismissNotices() {
  try { await Promise.all(notices.value.map(row => readFollowUpNotice(row.id))); await loadNotices() }
  catch { error.value = t("Some notices could not be dismissed. Try again.") }
}
function actionable(row: FollowUp) {
  return row.status !== 'SENT' && !row.archived_at && (!row.snoozed_until || new Date(row.snoozed_until).getTime() <= Date.now())
}
async function load() {
  void loadRecipients()
  const version = ++requestVersion
  busy.value = true; error.value = ''
  try {
    const query = new URLSearchParams({ page: String(page.value), page_size: '20', status: status.value, due: due.value, q: q.value, archived: String(archived.value), recipient: recipient.value, ...(paused.value ? { paused: paused.value } : {}) })
    const result = await getFollowUps('?' + query)
    if (version === requestVersion) {
      data.value = result
      const last = Math.max(1, Math.ceil(result.total / 20))
      if (page.value > last) page.value = last
    }
  } catch (reason) { if (version === requestVersion) error.value = reason instanceof Error ? reason.message : t("Unable to load follow-ups.") }
  finally { if (version === requestVersion) busy.value = false }
}
async function route() {
  const version = ++routeVersion
  const match = window.location.hash.match(/^#\/followups\/([^/]+)\/([^/]+)$/)
  if (!match) { selected.value = null; return }
  try {
    const [work, application] = await Promise.all([getWork(match[1]!), getApplication(match[1]!)])
    const item = work.followups.find(row => row.id === match[2])
    if (version !== routeVersion) return
    if (item) selected.value = { item, application }
    else { selected.value = null; error.value = t("Follow-up not found.") }
  } catch (reason) { if (version === routeVersion) error.value = reason instanceof Error ? reason.message : t("Unable to open follow-up.") }
}
function filter() { if (page.value === 1) void load(); else page.value = 1 }
async function changed() { await route(); await Promise.all([load(), loadNotices()]) }
watch(page, load)
watch(reviewPage, loadReviews)
function invalidate() { void load(); void loadNotices() }
onMounted(() => { void load(); void route(); void loadNotices(); noticeTimer = setInterval(loadNotices, 60000); recipientTimer = setInterval(() => { if (recipientQueue.value?.queued || recipientQueue.value?.running) void loadRecipients() }, 2000); window.addEventListener('hashchange', route); window.addEventListener('tracker:invalidate', invalidate) })
onUnmounted(() => { requestVersion++; routeVersion++; recipientVersion++; clearInterval(noticeTimer); clearInterval(recipientTimer); window.removeEventListener('hashchange', route); window.removeEventListener('tracker:invalidate', invalidate) })
</script>

<template>
  <section aria-labelledby="followup-title"><div class="page-heading"><div><h2 id="followup-title">{{ t("Follow-ups") }}</h2></div><Button type="button" severity="secondary" :disabled="busy" @click="changed">{{ t("Refresh") }}</Button></div><p v-if="!selected" class="intro">{{ t("Review your next follow-up.") }}</p>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <p v-if="selected"><a href="#/followups">{{ t("← All follow-ups") }}</a></p>
    <FollowUpEditor v-if="selected" :key="selected.item.id" :item="selected.item" :application="selected.application" @changed="changed" />
    <PageTabs v-else :label="t('Follow-up views')" :tabs="[{ value: 'queue', get label() { return t('Messages') }, icon: 'pi-envelope', count }, { value: 'recipients', get label() { return t('Recipients') }, icon: 'pi-users', count: recipientQueue?.missing_followups }, { value: 'attention', get label() { return t('Needs attention') }, icon: 'pi-exclamation-circle', count: (reviews?.total ?? 0) + notices.length }]">
    <template #queue>
    <details class="queue-filters"><summary>{{ t("Filters") }}</summary><form class="filters" @submit.prevent="filter"><label>{{ t("Find a job") }}<input v-model="q" type="search" :placeholder="t('Company or position')" /></label><label>{{ t("Recipient") }}<select v-model="recipient" @change="filter"><option value="">{{ t("All") }}</option><option value="missing">{{ t("Recipient needed") }}</option><option value="assigned">{{ t("Recipient assigned") }}</option></select></label><label>{{ t("State") }}<select v-model="status" @change="filter"><option value="">{{ t("Unsent") }}</option><option value="PREPARED">{{ t("Prepared") }}</option><option value="READY">{{ t("Ready") }}</option><option value="SENT">{{ t("Sent") }}</option></select></label><label>{{ t("Due") }}<select v-model="due" @change="filter"><option value="">{{ t("Any date") }}</option><option value="overdue">{{ t("Overdue") }}</option><option value="upcoming">{{ t("Upcoming") }}</option></select></label><label>{{ t("Job reminders") }}<select v-model="paused" @change="filter"><option value="">{{ t("All jobs") }}</option><option value="false">{{ t("Active") }}</option><option value="true">{{ t("Paused") }}</option></select></label><label class="check"><input v-model="archived" type="checkbox" @change="filter" /> {{ t("Archived") }}</label><Button type="submit" :disabled="busy">{{ t("Search") }}</Button></form></details>


    <p aria-live="polite">{{ busy ? t("Loading…") : t("{p0} follow-ups", { p0: count }) }}</p>
    <p>{{ t("Newest applications first") }}</p><div class="queue"><article v-for="row in data?.items ?? []" :key="row.id" class="row" :class="{ overdue: new Date(row.due_at!).getTime() < Date.now() && actionable(row) && !row.application.followup_paused }"><div><a :href="`#/followups/${row.application.id}/${row.id}`"><strong>{{ row.application.company }}</strong> · {{ row.application.job_title }}</a><p>#{{ row.sequence_number }} · {{ row.channel === 'BOTH' ? t("Email + phone") : messageText(row.channel.toLowerCase()) }} {{ t("· Due") }} {{ new Date(row.due_at!).toLocaleString(intlLocale) }}</p><p v-if="row.snoozed_until">{{ t("Snoozed until") }} {{ new Date(row.snoozed_until).toLocaleString(intlLocale) }}</p></div><div class="tags"><FollowUpTarget :status="followupTargetStatus(row.application, row)" /><AppTag v-bind="followupStatusMeta[row.status]" /><AppTag v-if="actionable(row) && !row.application.followup_paused" v-bind="urgencyMeta(row.due_at)" /><span v-if="row.application.followup_paused">{{ t("Paused") }}</span><span v-if="row.archived_at">{{ t("Archived") }}</span></div></article><p v-if="data && !data.items.length" class="empty">{{ t("No follow-ups match these filters.") }}</p><Pagination v-model:page="page" :total="count" :page-size="20" :label="t('follow-ups')" /></div>
    </template><template #recipients>    <div class="recipient-status"><p>{{ recipientQueue?.missing_followups ?? '…' }} {{ t("email follow-ups need a recipient.") }}</p><div class="recipient-actions"><Button type="button" severity="secondary" :disabled="queuing" @click="controlRecipients(recipientQueue?.paused ? resumeRecipientQueue : pauseRecipientQueue)">{{ recipientQueue?.paused ? t('Resume searches') : t('Pause all searches') }}</Button><Button type="button" :disabled="queuing || !recipientQueue?.available || !recipientQueue.missing_followups" @click="queueMissing">{{ t("Fetch missing recipients") }}</Button><label>{{ t("Recipient") }}<select v-model="recipient" @change="filter"><option value="">{{ t("All") }}</option><option value="missing">{{ t("Recipient needed") }}</option><option value="assigned">{{ t("Recipient assigned") }}</option></select></label><BusyIndicator v-if="recipientQueue?.running || recipientQueue?.queued" :label="t('{p0} finding recipients · {p1} queued · maximum 5 running', { p0: recipientQueue.running, p1: recipientQueue.queued })" /></div><p v-if="recipientQueue?.paused" role="status">{{ t('Queue paused. Resume to run prioritized searches. Saved reports are kept.') }}</p><ol v-if="recipientQueue?.jobs?.length" class="recipient-jobs"><li v-for="job in recipientQueue.jobs" :key="job.id"><div><a :href="`#/applications/${job.application_id}`">{{ job.company }} · {{ job.job_title }}</a><p>{{ messageText(job.state) }}</p></div><div class="recipient-actions"><Button v-if="job.state === 'QUEUED' || job.state === 'RUNNING'" severity="secondary" :disabled="queuing" @click="controlRecipients(() => pauseRecipientSearch(job.application_id))">{{ t('Pause search') }}</Button><Button v-if="job.state !== 'RUNNING'" :disabled="queuing" @click="controlRecipients(() => prioritizeRecipientSearch(job.application_id))">{{ t('Run next') }}</Button></div></li></ol><p v-if="queuedNotice" role="status">{{ queuedNotice }}</p><p v-if="recipientQueue && !recipientQueue.available">{{ t("Discovery is unavailable. You can enter a known address in each follow-up.") }}</p></div>
</template><template #attention><p v-if="!reviews?.total && !notices.length" class="empty">{{ t("Nothing needs review right now.") }}</p>    <details v-if="reviews?.total" class="at-message warning"><summary>{{ reviews.total }} {{ reviews.total === 1 ? t("application may") : t("applications may") }} {{ t("be unsuccessful · review needed") }}</summary><p>{{ t("These applications stay open. Review their outcomes or record an employer reply in the job notes.") }}</p><ul><li v-for="review in reviews.items" :key="review.application.id"><a :href="`#/applications/${review.application.id}`">{{ review.application.company }} · {{ review.application.job_title }}</a> — {{ review.unanswered_sent_count }} {{ t("unanswered follow-ups") }}</li></ul><Pagination v-model:page="reviewPage" :total="reviews.total" :page-size="20" :label="t('outcome reviews')" /></details>
    <details v-if="notices.length" class="at-message warning"><summary>{{ notices.length }} {{ t("follow-up reminders need attention") }}</summary><ul><li v-for="reminder in notices" :key="reminder.id"><a :href="`#/followups/${reminder.application.id}/${reminder.followup.id}`">{{ reminder.application.company }} · {{ reminder.application.job_title }}</a> — {{ messageText(String((reminder.followup.status === 'READY' ? t("ready for manual sending") : t("review prepared message")) ?? '')) }}</li></ul><Button type="button" severity="secondary" @click="dismissNotices">{{ t("Dismiss these notices") }}</Button><p>{{ t("Dismissal keeps messages in the queue and suppresses pending phone reminders. Delivered notifications may remain on your phone.") }}</p></details>
</template></PageTabs>
  </section>
</template>

<style scoped>
.recipient-jobs{padding-left:24px}.recipient-jobs li{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid var(--at-border)}.queue-filters{margin:16px 0}.queue-filters>summary{cursor:pointer;font-weight:600;padding:14px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}.queue-filters[open]>summary{margin-bottom:8px}.recipient-status{margin:16px 0;padding:14px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}.recipient-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.recipient-needed{color:var(--at-unsuccessful);font-weight:600}
.filters{display:flex;align-items:end;gap:12px;flex-wrap:wrap;padding:14px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}label{font-weight:600;font-size:13px}input,select{display:block;font:inherit;margin-top:6px;padding:9px;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}.check{display:flex;align-items:center;gap:8px;padding:10px}.check input{margin:0}.queue{border:1px solid var(--at-border);background:var(--at-surface);border-radius:8px}.row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:16px;padding:12px 16px;border-bottom:1px solid var(--at-border)}.row p{margin:5px 0 0;color:var(--at-text-muted);font-size:12px}.row.overdue{border-left:3px solid var(--at-unsuccessful);background:color-mix(in srgb,var(--at-unsuccessful) 5%,var(--at-surface))}.tags{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.empty{padding:20px}@media(max-width:700px){.row{grid-template-columns:1fr}.filters label{flex:1 1 140px}.filters input,.filters select{width:100%}}
</style>
