<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getTimeline, undoLastChange, type Timeline } from './api'

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ undone: [] }>()
const timeline = ref<Timeline | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const icons: Record<string, string> = {
  APPLICATION_CREATED: '+', APPLICATION_UPDATED: '✎', STATUS_CHANGED: '→', OUTCOME_CHANGED: '✓',
  POSTING_STATUS_CHANGED: '↗', NOTE_ADDED: 'N', NOTE_CHANGED: 'N', TASK_CREATED: 'T', TASK_CHANGED: 'T',
  TASK_COMPLETED: '✓', FOLLOWUP_CREATED: 'F', FOLLOWUP_DRAFTED: 'F', FOLLOWUP_SENT: '✓',
  FOLLOWUP_CHANGED: 'F', INTERVIEW_CREATED: 'I', INTERVIEW_CHANGED: 'I', INTERVIEW_DELETED: 'I', UNDO: '↶',
}

function dateText(value: string) {
  return new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

async function load() {
  busy.value = true; error.value = ''
  try { timeline.value = await getTimeline(props.applicationId) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load activity.' }
  finally { busy.value = false }
}

async function undo() {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await undoLastChange(props.applicationId)
    notice.value = `Restored ${result.fields.join(', ')}.`
    emit('undone')
    timeline.value = await getTimeline(props.applicationId)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to undo the change.' }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <section class="panel timeline-panel" aria-labelledby="timeline-title">
    <div class="timeline-heading"><div><h3 id="timeline-title">Timeline <span>{{ timeline?.events.length ?? 0 }}</span></h3><p class="hint">Changes by people, agents, and the system appear here.</p></div><div class="actions"><button v-if="timeline?.undo_available" type="button" :disabled="busy" @click="undo">Undo last change</button><button type="button" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Refresh timeline' }}</button></div></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="!timeline && busy" role="status">Loading activity…</p><p v-else-if="timeline && !timeline.events.length" class="hint">No activity recorded yet.</p>
    <ol v-if="timeline?.events.length" class="timeline"><li v-for="event in timeline.events" :key="event.id" :class="`event-${event.event_type.toLowerCase()}`"><span class="icon" aria-hidden="true">{{ icons[event.event_type] ?? '•' }}</span><div><strong>{{ event.summary }}</strong><p>{{ dateText(event.created_at) }} · {{ event.actor_type }}<template v-if="event.actor_reference"> · {{ event.actor_reference }}</template></p></div></li></ol>
  </section>
</template>

<style scoped>
.timeline-panel { margin-top: 32px; }.timeline-heading, .actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }.timeline-heading h3 { margin-bottom: 4px; }.timeline-heading h3 span { color: #627084; font-size: 13px; font-weight: 400; }.hint { color: #576678; font-size: 13px; line-height: 1.5; margin: 4px 0; }.notice { color: #216344; font-size: 14px; }.timeline { list-style: none; padding: 0; margin: 22px 0 0; }.timeline li { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; position: relative; padding-bottom: 20px; }.timeline li:not(:last-child)::before { content: ''; position: absolute; left: 16px; top: 32px; bottom: 0; width: 2px; background: #dce2e9; }.icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: #eaf1fc; color: #2a5189; font-size: 14px; font-weight: 700; z-index: 1; }.timeline strong { font-size: 14px; }.timeline p { color: #627084; font-size: 12px; margin: 5px 0 0; }.event-task_completed .icon, .event-followup_sent .icon, .event-outcome_changed .icon { background: #eaf5ee; color: #216344; }.event-undo .icon { background: #fff1de; color: #844d15; }.event-interview_created .icon, .event-interview_changed .icon { background: #f0e9fa; color: #654388; }
</style>
