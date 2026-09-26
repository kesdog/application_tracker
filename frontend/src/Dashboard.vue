<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getDashboard, type DashboardData } from './api'
import { dateTimeText, relativeDateText } from './dateText'
import Pagination from './Pagination.vue'

const dashboard = ref<DashboardData | null>(null)
const loading = ref(false)
const error = ref('')
const followupPage = ref(1)
const followupPageSize = 10
const cards = computed(() => dashboard.value ? [
  { label: 'Active applications', value: dashboard.value.counts.active_applications, tone: 'neutral' },
  { label: 'Tasks due', value: dashboard.value.counts.tasks_due, tone: 'neutral' },
  { label: 'Tasks overdue', value: dashboard.value.counts.tasks_overdue, tone: 'urgent' },
  { label: 'Follow-ups due', value: dashboard.value.counts.followups_due, tone: 'neutral' },
  { label: 'Follow-ups overdue', value: dashboard.value.counts.followups_overdue, tone: 'urgent' },
  { label: 'Upcoming interviews', value: dashboard.value.counts.upcoming_interviews, tone: 'interview' },
] : [])
const followups = computed(() => dashboard.value
  ? [...dashboard.value.overdue_followups, ...dashboard.value.due_followups].sort((a, b) => a.due_at.localeCompare(b.due_at))
  : [])
const visibleFollowups = computed(() => followups.value.slice((followupPage.value - 1) * followupPageSize, followupPage.value * followupPageSize))

function urgency(dueAt: string) {
  const due = new Date(dueAt)
  const now = new Date()
  if (due.getTime() < now.getTime()) return 'overdue'
  if (due.toDateString() === now.toDateString()) return 'today'
  if (due.getTime() - now.getTime() <= 3 * 24 * 60 * 60 * 1000) return 'soon'
  return 'scheduled'
}

async function load() {
  loading.value = true; error.value = ''
  try { dashboard.value = await getDashboard(); followupPage.value = 1 }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load dashboard.' }
  finally { loading.value = false }
}

const onInvalidation = () => { void load() }
onMounted(() => { void load(); window.addEventListener('tracker:invalidate', onInvalidation) })
onUnmounted(() => window.removeEventListener('tracker:invalidate', onInvalidation))
</script>

<template>
  <section aria-labelledby="dashboard-title">
    <div class="page-heading"><div><p class="eyebrow">Your workspace</p><h2 id="dashboard-title">Dashboard</h2></div><button type="button" :disabled="loading" @click="load">{{ loading ? 'Loading…' : 'Refresh' }}</button></div>
    <p class="intro">See what needs attention next.</p><p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading && !dashboard" role="status">Loading dashboard…</p>
    <template v-if="dashboard">
      <div class="metrics"><article v-for="card in cards" :key="card.label" class="metric" :class="card.tone"><strong>{{ card.value }}</strong><span>{{ card.label }}</span></article></div>
      <section class="panel followups-panel"><div class="section-heading"><div><h3>Follow-ups</h3><p>Overdue and upcoming reminders in one queue.</p></div><span>{{ followups.length }}</span></div><p v-if="!followups.length" class="empty">No follow-ups are due in the next seven days.</p><div v-else class="table-scroll" tabindex="0" role="region" aria-label="Follow-ups"><table><thead><tr><th>Due</th><th>Application</th><th>Company</th><th>Status</th></tr></thead><tbody><tr v-for="item in visibleFollowups" :key="item.id" :class="`urgency-${urgency(item.due_at)}`"><td><strong>{{ relativeDateText(item.due_at, 'due ') }}</strong><small>{{ dateTimeText(item.due_at) }}</small></td><td><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a></td><td>{{ item.application.company }}</td><td><span class="urgency-badge" :class="urgency(item.due_at)">{{ urgency(item.due_at) }}</span></td></tr></tbody></table><Pagination v-model:page="followupPage" :total="followups.length" :page-size="followupPageSize" label="follow-ups" /></div></section>
      <section class="panel recent-panel"><div class="section-heading"><h3>Recent activity</h3><span>{{ dashboard.recent_activity.length }}</span></div><p v-if="!dashboard.recent_activity.length" class="empty">No recent activity.</p><ol v-else class="items activity"><li v-for="event in dashboard.recent_activity" :key="event.id"><div><strong>{{ event.summary }}</strong><p><a :href="`#/applications/${event.application.id}`">{{ event.application.job_title }}</a> · {{ event.application.company }}</p><small>{{ dateTimeText(event.created_at) }} · {{ event.actor_type }}</small></div></li></ol></section>
    </template>
  </section>
</template>

<style scoped>
.page-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 20px; }.metric { display: flex; flex-direction: column; gap: 3px; background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 14px; }.metric strong { font-size: 23px; color: #263e5c; }.metric span, .section-heading span { color: #576678; font-size: 12px; }.metric.urgent { border-top: 3px solid #b33b42; }.metric.urgent strong { color: #9d2930; }.metric.interview { border-top: 3px solid #6b4c91; }.panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 18px; margin-top: 18px; }.section-heading p { color:#627084; font-size:12px; margin:4px 0 0; }.table-scroll { overflow-x:auto; } table { width:100%; border-collapse:collapse; text-align:left; font-size:13px; } th { background:#f3f6f8; color:#526174; font-size:11px; text-transform:uppercase; letter-spacing:.03em; } th, td { padding:10px 12px; border-bottom:1px solid #e5e9ee; } td small { display:block; color:#627084; font-size:11px; margin-top:3px; white-space:nowrap; } .urgency-overdue { background:#fff1f1; box-shadow:inset 3px 0 #b33b42; }.urgency-today { background:#fff8e8; box-shadow:inset 3px 0 #b7791f; }.urgency-soon { background:#f3f8ff; box-shadow:inset 3px 0 #3e73a8; }.urgency-badge { display:inline-block; border-radius:999px; padding:3px 7px; font-size:10px; font-weight:700; text-transform:uppercase; }.urgency-badge.overdue { color:#972b32; background:#fcebed; }.urgency-badge.today { color:#855410; background:#fff1d4; }.urgency-badge.soon { color:#235888; background:#eaf2fb; }.urgency-badge.scheduled { color:#526174; background:#edf0f3; }.items { list-style:none; padding:0; margin:12px 0 0; }.items li { padding:10px 0; border-top:1px solid #e5e9ee; }.items p, .items small { color:#627084; font-size:12px; margin:4px 0 0; }.activity li { display:block; }.empty { color:#576678; font-size:14px; margin:18px 0 0; }a { color:#24568b; text-underline-offset:3px; }
@media (max-width:800px) { .metrics { grid-template-columns:repeat(2, minmax(0, 1fr)); } }@media (max-width:480px) { .metrics { grid-template-columns:1fr; }.panel { padding:14px; } }
</style>
