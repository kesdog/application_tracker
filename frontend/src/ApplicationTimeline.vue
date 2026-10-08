<script setup lang="ts">
import Button from 'primevue/button'
import DateTimeField from './components/shared/DateTimeField.vue'
import InputText from 'primevue/inputtext'
import { onMounted, reactive, ref } from 'vue'
import { createTimelineEntry, getTimeline, undoLastChange, updateTimelineEntry, type Timeline, type TimelineEvent } from './api'
import EmailReference from './EmailReference.vue'
import PrimeTimeline from 'primevue/timeline'
import { actorLabels, timelineEventMeta } from './presentation/timelinePresentation'
import { appearanceVariable } from './settings/applyAppearance'

function emailSummary(event: TimelineEvent) {
  if (event.event_type !== 'MANUAL') return { text: event.summary, reference: null }
  const reference = event.summary.match(/https?:\/\/[^\s<>]+/)?.[0] ?? event.summary.match(/\[Gmail:[a-f0-9]+\]/i)?.[0] ?? null
  return { text: reference ? event.summary.replace(reference, '').trim() : event.summary, reference }
}

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ undone: [] }>()
const timeline = ref<Timeline | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const entryOpen = ref(false)
const entryForm = reactive({ id: '', summary: '', occurred_at: '' })

function markerStyle(type: string) {
  const tone = timelineEventMeta(type).tone
  const variable = appearanceVariable(tone === 'neutral' ? 'surfaceMuted' : tone)
  return { background: `var(${variable})`, color: `var(${variable}-contrast)` }
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
    <div class="timeline-heading"><div><h3 id="timeline-title">Timeline <span>{{ timeline?.events.length ?? 0 }}</span></h3><p class="hint">Submitted-on entries use the recorded application date. Add an email event when you need the exact sent or received time.</p></div><div class="actions"><Button v-if="!entryOpen" type="button" :disabled="busy" @click="openEntry()">Add email event</Button><Button v-if="timeline?.undo_available" type="button" :disabled="busy" @click="undo">Undo last change</Button><Button type="button" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Refresh timeline' }}</Button></div></div>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <form v-if="entryOpen" class="entry-form" @submit.prevent="saveEntry"><fieldset :disabled="busy"><legend>{{ entryForm.id ? 'Edit email timeline entry' : 'Add email timeline entry' }}</legend><label>What happened<InputText class="at-form-control" v-model="entryForm.summary" required maxlength="500" placeholder="e.g. Submitted technical task by email" /></label><DateTimeField v-model="entryForm.occurred_at" label="Email time (local)" :disabled="busy" required /><div class="actions"><Button class="primary" type="submit">Save entry</Button><Button type="button" @click="entryOpen = false">Cancel</Button></div></fieldset></form>
    <p v-if="!timeline && busy" role="status">Loading activity…</p><p v-else-if="timeline && !timeline.events.length" class="hint">No activity recorded yet.</p>
    <PrimeTimeline v-if="timeline?.events.length" :value="timeline.events" class="activity-timeline" aria-label="Application activity">
      <template #marker="{ item }"><span class="event-marker" :style="markerStyle(item.event_type)"><i :class="timelineEventMeta(item.event_type).icon" aria-hidden="true" /></span></template>
      <template #content="{ item }"><div class="event-content"><div class="event-heading"><strong>{{ emailSummary(item).text }} <EmailReference v-if="emailSummary(item).reference" :reference="emailSummary(item).reference" /></strong><Button v-if="item.event_type === 'MANUAL'" type="button" severity="secondary" text :disabled="busy" @click="openEntry(item)">Edit</Button></div><p>{{ dateText(item) }} · {{ actorLabels[item.actor_type as keyof typeof actorLabels] }}<template v-if="item.actor_reference"> · {{ item.actor_reference }}</template></p></div></template>
    </PrimeTimeline>
  </section>
</template>

<style scoped>
@layer legacy {
.timeline-panel { margin-top: 32px; }.timeline-heading, .actions, .event-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }.timeline-heading h3 { margin-bottom: 4px; }.timeline-heading h3 span { color: var(--at-text-muted); font-size: 13px; font-weight: 400; }.hint { color: var(--at-text-muted); font-size: 13px; line-height: 1.5; margin: 4px 0; }.notice { color: var(--at-successful); font-size: 14px; }.entry-form { border-top: 1px solid var(--at-border); margin-top: 18px; padding-top: 18px; }.entry-form fieldset { border: 0; margin: 0; padding: 0; }.entry-form legend { font-size: 14px; font-weight: 650; }.entry-form label { display: block; font-size: 14px; font-weight: 600; margin-top: 12px; }.entry-form input { display: block; width: 100%; margin-top: 6px; padding: 10px; border: 1px solid var(--at-border); border-radius: 5px; font: inherit; }.primary { background: var(--at-primary); border-color: var(--at-primary); color:var(--at-primary-contrast); }.timeline { list-style: none; padding: 0; margin: 22px 0 0; }.timeline li { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; position: relative; padding-bottom: 20px; }.timeline li:not(:last-child)::before { content: ''; position: absolute; left: 16px; top: 32px; bottom: 0; width: 2px; background: var(--at-border); }.icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: color-mix(in srgb, var(--at-submitted) 10%, var(--at-surface)); color: var(--at-submitted); font-size: 14px; font-weight: 700; z-index: 1; }.timeline strong { font-size: 14px; }.timeline p { color: var(--at-text-muted); font-size: 12px; margin: 5px 0 0; }.event-manual .icon { background: color-mix(in srgb, var(--at-cancelled) 10%, var(--at-surface)); color: var(--at-cancelled); }.event-task_completed .icon, .event-followup_sent .icon, .event-outcome_changed .icon { background: color-mix(in srgb, var(--at-successful) 10%, var(--at-surface)); color: var(--at-successful); }.event-undo .icon { background: color-mix(in srgb, var(--at-cancelled) 10%, var(--at-surface)); color: var(--at-cancelled); }.event-interview_created .icon, .event-interview_changed .icon { background: color-mix(in srgb, var(--at-interview) 10%, var(--at-surface)); color: var(--at-interview); }
}
</style>
