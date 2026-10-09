<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import Pagination from './Pagination.vue'
import AppTag from './components/shared/AppTag.vue'
import FollowUpEditor from './FollowUpEditor.vue'
import { getFollowUps, getWork, getApplication, getFollowUpNotices, readFollowUpNotice, type FollowUpNotice, type FollowUpPage, type FollowUp, type Application } from './api'
import { followupStatusMeta, urgencyMeta } from './presentation/taskPresentation'
const data = ref<FollowUpPage | null>(null)
const page = ref(1)
const status = ref('')
const due = ref('')
const q = ref('')
const archived = ref(false)
const paused = ref('')
const selected = ref<{ item: FollowUp; application: Application } | null>(null)
const busy = ref(false)
const error = ref('')
const count = computed(() => data.value?.total ?? 0)
const notices = ref<FollowUpNotice[]>([])
let requestVersion = 0
let routeVersion = 0
let noticeTimer: ReturnType<typeof setInterval> | undefined
async function loadNotices() {
  try { notices.value = await getFollowUpNotices() } catch { /* Queue remains usable if notices are unavailable. */ }
}
async function dismissNotices() {
  try { await Promise.all(notices.value.map(row => readFollowUpNotice(row.id))); await loadNotices() }
  catch { error.value = 'Some notices could not be dismissed. Try again.' }
}
function actionable(row: FollowUp) {
  return row.status !== 'SENT' && !row.archived_at && (!row.snoozed_until || new Date(row.snoozed_until).getTime() <= Date.now())
}
async function load() {
  const version = ++requestVersion
  busy.value = true; error.value = ''
  try {
    const query = new URLSearchParams({ page: String(page.value), page_size: '20', status: status.value, due: due.value, q: q.value, archived: String(archived.value), ...(paused.value ? { paused: paused.value } : {}) })
    const result = await getFollowUps('?' + query)
    if (version === requestVersion) {
      data.value = result
      const last = Math.max(1, Math.ceil(result.total / 20))
      if (page.value > last) page.value = last
    }
  } catch (reason) { if (version === requestVersion) error.value = reason instanceof Error ? reason.message : 'Unable to load follow-ups.' }
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
    else { selected.value = null; error.value = 'Follow-up not found.' }
  } catch (reason) { if (version === routeVersion) error.value = reason instanceof Error ? reason.message : 'Unable to open follow-up.' }
}
function filter() { if (page.value === 1) void load(); else page.value = 1 }
async function changed() { await route(); await Promise.all([load(), loadNotices()]) }
watch(page, load)
function invalidate() { void load(); void loadNotices() }
onMounted(() => { void load(); void route(); void loadNotices(); noticeTimer = setInterval(loadNotices, 60000); window.addEventListener('hashchange', route); window.addEventListener('tracker:invalidate', invalidate) })
onUnmounted(() => { requestVersion++; routeVersion++; clearInterval(noticeTimer); window.removeEventListener('hashchange', route); window.removeEventListener('tracker:invalidate', invalidate) })
</script>

<template>
  <section aria-labelledby="followup-title"><div class="page-heading"><div><p class="eyebrow">Your next contact</p><h2 id="followup-title">Follow-ups</h2></div><Button type="button" severity="secondary" :disabled="busy" @click="changed">Refresh</Button></div><p class="intro">Prepared messages and reminders, with or without an AI agent.</p>
    <form class="filters" @submit.prevent="filter"><label>Find a job<input v-model="q" type="search" placeholder="Company or position" /></label><label>State<select v-model="status" @change="filter"><option value="">Unsent</option><option value="PREPARED">Prepared</option><option value="READY">Ready</option><option value="SENT">Sent</option></select></label><label>Due<select v-model="due" @change="filter"><option value="">Any date</option><option value="overdue">Overdue</option><option value="upcoming">Upcoming</option></select></label><label>Job reminders<select v-model="paused" @change="filter"><option value="">All jobs</option><option value="false">Active</option><option value="true">Paused</option></select></label><label class="check"><input v-model="archived" type="checkbox" @change="filter" /> Archived</label><Button type="submit" :disabled="busy">Search</Button></form>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p>
    <details v-if="notices.length" class="at-message warning"><summary>{{ notices.length }} follow-up reminders need attention</summary><ul><li v-for="reminder in notices" :key="reminder.id"><a :href="`#/followups/${reminder.application.id}/${reminder.followup.id}`">{{ reminder.application.company }} · {{ reminder.application.job_title }}</a> — {{ reminder.followup.status === 'READY' ? 'ready for manual sending' : 'review prepared message' }}</li></ul><Button type="button" severity="secondary" @click="dismissNotices">Dismiss these notices</Button><p>Dismissal keeps messages in the queue and suppresses pending phone reminders. Delivered notifications may remain on your phone.</p></details>
    <FollowUpEditor v-if="selected" :key="selected.item.id" :item="selected.item" :application="selected.application" @changed="changed" />
    <p v-if="selected"><a href="#/followups">Close message</a></p><p aria-live="polite">{{ busy ? 'Loading…' : `${count} follow-ups` }}</p>
    <div class="queue"><article v-for="row in data?.items ?? []" :key="row.id" class="row" :class="{ overdue: new Date(row.due_at!).getTime() < Date.now() && actionable(row) && !row.application.followup_paused }"><div><a :href="`#/followups/${row.application.id}/${row.id}`"><strong>{{ row.application.company }}</strong> · {{ row.application.job_title }}</a><p>#{{ row.sequence_number }} · {{ row.channel === 'BOTH' ? 'Email + phone' : row.channel.toLowerCase() }} · Due {{ new Date(row.due_at!).toLocaleString() }}</p><p v-if="row.snoozed_until">Snoozed until {{ new Date(row.snoozed_until).toLocaleString() }}</p></div><div class="tags"><AppTag v-bind="followupStatusMeta[row.status]" /><AppTag v-if="actionable(row) && !row.application.followup_paused" v-bind="urgencyMeta(row.due_at)" /><span v-if="row.application.followup_paused">Paused</span><span v-if="row.archived_at">Archived</span></div><a :href="`#/followups/${row.application.id}/${row.id}`">{{ row.status === 'READY' ? 'Review and send' : row.status === 'SENT' ? 'View record' : 'Review message' }}</a></article><p v-if="data && !data.items.length" class="empty">No follow-ups match these filters.</p><Pagination v-model:page="page" :total="count" :page-size="20" label="follow-ups" /></div>
  </section>
</template>

<style scoped>
.filters{display:flex;align-items:end;gap:12px;flex-wrap:wrap;padding:14px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}label{font-weight:600;font-size:13px}input,select{display:block;font:inherit;margin-top:6px;padding:9px;background:var(--at-surface);color:var(--at-text);border:1px solid var(--at-border);border-radius:5px}.check{display:flex;align-items:center;gap:8px;padding:10px}.check input{margin:0}.queue{border:1px solid var(--at-border);background:var(--at-surface);border-radius:8px}.row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:16px;padding:12px 16px;border-bottom:1px solid var(--at-border)}.row p{margin:5px 0 0;color:var(--at-text-muted);font-size:12px}.row.overdue{border-left:3px solid var(--at-unsuccessful);background:color-mix(in srgb,var(--at-unsuccessful) 5%,var(--at-surface))}.tags{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.empty{padding:20px}@media(max-width:700px){.row{grid-template-columns:1fr}.filters label{flex:1 1 140px}.filters input,.filters select{width:100%}}
</style>
