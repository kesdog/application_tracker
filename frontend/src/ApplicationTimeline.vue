<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createTimelineEntry, getTimeline, undoLastChange, updateTimelineEntry, type Timeline, type TimelineEvent } from './api'

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ undone: [] }>()
const timeline = ref<Timeline | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const entryOpen = ref(false)
const entryForm = reactive({ id: '', summary: '', occurred_at: '' })

const icons: Record<string, string> = {
  APPLICATION_CREATED: '+', APPLICATION_SUBMITTED: '↗', APPLICATION_UPDATED: '✎', STATUS_CHANGED: '→', OUTCOME_CHANGED: '✓',
  POSTING_STATUS_CHANGED: '↗', NOTE_ADDED: 'N', NOTE_CHANGED: 'N', TASK_CREATED: 'T', TASK_CHANGED: 'T',
  TASK_COMPLETED: '✓', FOLLOWUP_CREATED: 'F', FOLLOWUP_DRAFTED: 'F', FOLLOWUP_SENT: '✓',
  FOLLOWUP_CHANGED: 'F', INTERVIEW_CREATED: 'I', INTERVIEW_CHANGED: 'I', INTERVIEW_DELETED: 'I', UNDO: '↶', MANUAL: '✉',
}

function dateText(event: TimelineEvent) {
  if (event.metadata?.date_only && typeof event.metadata.date_applied === 'string') return event.metadata.date_applied
  return new Date(event.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}
function localDateTime(value: string) {
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
function openEntry(event?: TimelineEvent) {
  Object.assign(entryForm, event ? { id: event.id, summary: event.summary, occurred_at: localDateTime(event.created_at) } : { id: '', summary: '', occurred_at: localDateTime(new Date().toISOString()) })
  entryOpen.value = true
}

async function load() {
  busy.value = true; error.value = ''
  try { timeline.value = await getTimeline(props.applicationId) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load activity.' }
  finally { busy.value = false }
}

async function saveEntry() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const data = { summary: entryForm.summary, occurred_at: new Date(entryForm.occurred_at).toISOString() }
    const editing = Boolean(entryForm.id)
    if (editing) await updateTimelineEntry(props.applicationId, entryForm.id, data)
    else await createTimelineEntry(props.applicationId, data)
    entryOpen.value = false
    notice.value = editing ? 'Timeline entry updated.' : 'Email timeline entry added.'
    await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to save the timeline entry.' }
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
    <div class="timeline-heading"><div><h3 id="timeline-title">Timeline <span>{{ timeline?.events.length ?? 0 }}</span></h3><p class="hint">Submitted-on entries use the recorded application date. Add an email event when you need the exact sent or received time.</p></div><div class="actions"><button v-if="!entryOpen" type="button" :disabled="busy" @click="openEntry()">Add email event</button><button v-if="timeline?.undo_available" type="button" :disabled="busy" @click="undo">Undo last change</button><button type="button" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Refresh timeline' }}</button></div></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <form v-if="entryOpen" class="entry-form" @submit.prevent="saveEntry"><fieldset :disabled="busy"><legend>{{ entryForm.id ? 'Edit email timeline entry' : 'Add email timeline entry' }}</legend><label>What happened<input v-model="entryForm.summary" required maxlength="500" placeholder="e.g. Submitted technical task by email" /></label><label>Email time (local)<input v-model="entryForm.occurred_at" required type="datetime-local" /></label><div class="actions"><button class="primary" type="submit">Save entry</button><button type="button" @click="entryOpen = false">Cancel</button></div></fieldset></form>
    <p v-if="!timeline && busy" role="status">Loading activity…</p><p v-else-if="timeline && !timeline.events.length" class="hint">No activity recorded yet.</p>
    <ol v-if="timeline?.events.length" class="timeline"><li v-for="event in timeline.events" :key="event.id" :class="`event-${event.event_type.toLowerCase()}`"><span class="icon" aria-hidden="true">{{ icons[event.event_type] ?? '•' }}</span><div><div class="event-heading"><strong>{{ event.summary }}</strong><button v-if="event.event_type === 'MANUAL'" type="button" :disabled="busy" @click="openEntry(event)">Edit</button></div><p>{{ dateText(event) }} · {{ event.event_type === 'MANUAL' ? 'EMAIL' : event.actor_type }}<template v-if="event.actor_reference"> · {{ event.actor_reference }}</template></p></div></li></ol>
  </section>
</template>

<style scoped>
.timeline-panel { margin-top: 32px; }.timeline-heading, .actions, .event-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }.timeline-heading h3 { margin-bottom: 4px; }.timeline-heading h3 span { color: #627084; font-size: 13px; font-weight: 400; }.hint { color: #576678; font-size: 13px; line-height: 1.5; margin: 4px 0; }.notice { color: #216344; font-size: 14px; }.entry-form { border-top: 1px solid #dce2e9; margin-top: 18px; padding-top: 18px; }.entry-form fieldset { border: 0; margin: 0; padding: 0; }.entry-form legend { font-size: 14px; font-weight: 650; }.entry-form label { display: block; font-size: 14px; font-weight: 600; margin-top: 12px; }.entry-form input { display: block; width: 100%; margin-top: 6px; padding: 10px; border: 1px solid #b9c4d2; border-radius: 5px; font: inherit; }.primary { background: #263e5c; border-color: #263e5c; color: #fff; }.timeline { list-style: none; padding: 0; margin: 22px 0 0; }.timeline li { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; position: relative; padding-bottom: 20px; }.timeline li:not(:last-child)::before { content: ''; position: absolute; left: 16px; top: 32px; bottom: 0; width: 2px; background: #dce2e9; }.icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: #eaf1fc; color: #2a5189; font-size: 14px; font-weight: 700; z-index: 1; }.timeline strong { font-size: 14px; }.timeline p { color: #627084; font-size: 12px; margin: 5px 0 0; }.event-manual .icon { background: #fff1de; color: #844d15; }.event-task_completed .icon, .event-followup_sent .icon, .event-outcome_changed .icon { background: #eaf5ee; color: #216344; }.event-undo .icon { background: #fff1de; color: #844d15; }.event-interview_created .icon, .event-interview_changed .icon { background: #f0e9fa; color: #654388; }
</style>
