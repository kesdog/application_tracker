<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getDashboard, type DashboardData } from './api'
import { dateTimeText, relativeDateText } from './dateText'

const dashboard = ref<DashboardData | null>(null)
const loading = ref(false)
const error = ref('')
const cards = computed(() => dashboard.value ? [
  { label: 'Active applications', value: dashboard.value.counts.active_applications, tone: 'neutral' },
  { label: 'Tasks due', value: dashboard.value.counts.tasks_due, tone: 'neutral' },
  { label: 'Tasks overdue', value: dashboard.value.counts.tasks_overdue, tone: 'urgent' },
  { label: 'Follow-ups due', value: dashboard.value.counts.followups_due, tone: 'neutral' },
  { label: 'Follow-ups overdue', value: dashboard.value.counts.followups_overdue, tone: 'urgent' },
  { label: 'Upcoming interviews', value: dashboard.value.counts.upcoming_interviews, tone: 'interview' },
] : [])

async function load() {
  loading.value = true; error.value = ''
  try { dashboard.value = await getDashboard() }
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
      <div class="dashboard-grid">
        <section class="panel"><div class="section-heading"><h3>Upcoming work</h3><span>{{ dashboard.upcoming.length }}</span></div><p v-if="!dashboard.upcoming.length" class="empty">Nothing due in the next seven days.</p><ol v-else class="items"><li v-for="item in dashboard.upcoming" :key="`${item.kind}-${item.id}`"><span class="kind" :class="item.kind.toLowerCase()">{{ item.kind }}</span><div><strong>{{ item.title }} — {{ relativeDateText(item.due_at, item.kind === 'INTERVIEW' ? '' : 'due ') }}</strong><p><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }}</p><small>{{ dateTimeText(item.due_at) }} · {{ item.status }}</small></div></li></ol></section>
        <section class="panel"><div class="section-heading"><h3>Recent activity</h3><span>{{ dashboard.recent_activity.length }}</span></div><p v-if="!dashboard.recent_activity.length" class="empty">No recent activity.</p><ol v-else class="items activity"><li v-for="event in dashboard.recent_activity" :key="event.id"><div><strong>{{ event.summary }}</strong><p><a :href="`#/applications/${event.application.id}`">{{ event.application.job_title }}</a> · {{ event.application.company }}</p><small>{{ dateTimeText(event.created_at) }} · {{ event.actor_type }}</small></div></li></ol></section>
      </div>
      <div class="followup-grid">
        <section class="panel"><div class="section-heading"><h3>Follow-ups due soon</h3><span>{{ dashboard.due_followups.length }}</span></div><p v-if="!dashboard.due_followups.length" class="empty">No follow-ups are due in the next seven days.</p><ol v-else class="items"><li v-for="item in dashboard.due_followups" :key="item.id"><div><strong>{{ item.title }} — {{ relativeDateText(item.due_at, 'due ') }}</strong><p><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }}</p><small>{{ dateTimeText(item.due_at) }}</small></div></li></ol></section>
        <section class="panel overdue-panel"><div class="section-heading"><h3>Overdue follow-ups</h3><span>{{ dashboard.overdue_followups.length }}</span></div><p v-if="!dashboard.overdue_followups.length" class="empty">No overdue follow-ups.</p><ol v-else class="items"><li v-for="item in dashboard.overdue_followups" :key="item.id"><div><strong>{{ item.title }} — {{ relativeDateText(item.due_at, 'due ') }}</strong><p><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }}</p><small>{{ dateTimeText(item.due_at) }}</small></div></li></ol></section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.page-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 24px; }.metric { display: flex; flex-direction: column; gap: 5px; background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 18px; }.metric strong { font-size: 28px; color: #263e5c; }.metric span { color: #576678; font-size: 13px; }.metric.urgent { border-top: 4px solid #b33b42; }.metric.urgent strong { color: #9d2930; }.metric.interview { border-top: 4px solid #6b4c91; }.dashboard-grid, .followup-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 20px; align-items: start; }.followup-grid { margin-top: 20px; grid-template-columns: 1fr 1fr; }.panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 22px; }.overdue-panel { border-top: 4px solid #b33b42; }.section-heading span { color: #627084; font-size: 13px; }.items { list-style: none; padding: 0; margin: 18px 0 0; }.items li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; padding: 15px 0; border-top: 1px solid #e5e9ee; }.items p, .items small { color: #627084; font-size: 12px; margin: 5px 0 0; }.kind { align-self: start; font-size: 10px; font-weight: 700; color: #2a5189; background: #eaf1fc; border-radius: 4px; padding: 5px 7px; }.kind.interview { background: #f0e9fa; color: #654388; }.kind.followup { background: #fff1de; color: #844d15; }.activity li { grid-template-columns: 1fr; }.empty { color: #576678; font-size: 14px; margin: 22px 0 0; }a { color: #24568b; text-underline-offset: 3px; }
@media (max-width: 800px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.dashboard-grid, .followup-grid { grid-template-columns: 1fr; } }@media (max-width: 480px) { .metrics { grid-template-columns: 1fr; } }
</style>
