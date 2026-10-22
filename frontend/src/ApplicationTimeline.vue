<script setup lang="ts">
import Button from 'primevue/button'
import DateTimeField from './components/shared/DateTimeField.vue'
import InputText from 'primevue/inputtext'
import { onMounted, reactive, ref } from 'vue'
import { createTimelineEntry, getTimeline, undoLastChange, updateTimelineEntry, type Timeline, type TimelineEvent } from './api'
import EmailReference from './EmailReference.vue'
import { emailReferenceUrl } from './emailReference'
import PrimeTimeline from 'primevue/timeline'
import { actorLabels, timelineEventMeta } from './presentation/timelinePresentation'
import { appearanceVariable } from './settings/applyAppearance'

function emailSummary(event: TimelineEvent) {
  if (event.event_type === 'APPLICATION_SUBMITTED' && event.metadata?.date_only
    && event.summary === `Application submitted on ${event.metadata.date_applied}`) {
    return { text: 'Application submitted', reference: null }
  }
  if (event.event_type !== 'MANUAL') return { text: event.summary, reference: null }
  const references = event.summary.match(/https?:\/\/[^\s<>]+|\[Gmail:[a-f0-9]+\]/gi) ?? []
  const unique = new Map<string, string>()
  let text = event.summary
  for (const reference of references) {
    const url = emailReferenceUrl(reference)
    if (!url) continue
    unique.set(url, reference)
    text = text.replace(reference, '')
  }
  return { text: text.replace(/[ \t]{2,}/g, ' ').trim() || 'Email activity', reference: [...unique.values()].join('\n') || null }
}

const props = defineProps<{ applicationId: string; embedded?: boolean }>()
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
  <section class="panel timeline-panel" :class="{ embedded }" aria-label="Application timeline">
    <div class="timeline-heading"><h3 v-if="!embedded">Timeline</h3><span v-if="timeline" class="event-count">{{ timeline.events.length }} {{ timeline.events.length === 1 ? 'event' : 'events' }}</span><div class="actions"><Button v-if="!entryOpen" type="button" severity="secondary" outlined size="small" :disabled="busy" @click="openEntry()">Add email event</Button><Button v-if="timeline?.undo_available" type="button" severity="secondary" text size="small" :disabled="busy" @click="undo">Undo last change</Button><Button type="button" severity="secondary" text size="small" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Refresh' }}</Button></div></div>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <form v-if="entryOpen" class="entry-form" @submit.prevent="saveEntry"><fieldset :disabled="busy"><legend>{{ entryForm.id ? 'Edit email event' : 'New email event' }}</legend><label>What happened<InputText class="at-form-control" v-model="entryForm.summary" required maxlength="500" placeholder="e.g. Submitted technical task by email" /></label><DateTimeField v-model="entryForm.occurred_at" label="Email time (local)" :disabled="busy" required /><p class="hint">Use the email's sent or received time. Submission entries keep the application date.</p><div class="actions"><Button class="primary" type="submit">Save entry</Button><Button type="button" @click="entryOpen = false">Cancel</Button></div></fieldset></form>
    <p v-if="!timeline && busy" role="status">Loading activity…</p><p v-else-if="timeline && !timeline.events.length" class="hint">No activity recorded yet.</p>
    <PrimeTimeline v-if="timeline?.events.length" :value="timeline.events" class="activity-timeline" aria-label="Application activity">
      <template #marker="{ item }"><span class="event-marker" :style="markerStyle(item.event_type)" aria-hidden="true"><i :class="timelineEventMeta(item.event_type).icon" /></span></template>
      <template #content="{ item }"><div class="event-content"><div class="event-heading"><strong>{{ emailSummary(item).text }} <EmailReference v-if="emailSummary(item).reference" :reference="emailSummary(item).reference" /></strong><Button v-if="item.event_type === 'MANUAL'" type="button" severity="secondary" text size="small" :disabled="busy" @click="openEntry(item)">Edit</Button></div><p>{{ dateText(item) }} · {{ actorLabels[item.actor_type as keyof typeof actorLabels] }}<template v-if="item.actor_reference && !(item.actor_type === 'AGENT' && item.actor_reference === 'agent-token')"> · {{ item.actor_reference }}</template></p></div></template>
    </PrimeTimeline>
  </section>
</template>

<style scoped>
.timeline-panel { margin-top:24px; padding:20px; border:1px solid var(--at-border); border-radius:8px; background:var(--at-surface); }
.timeline-panel.embedded { margin:0; padding:0 20px 20px; border:0; border-radius:0; background:transparent; }
.timeline-heading, .actions, .event-heading { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.timeline-heading { margin-bottom:20px; }.timeline-heading h3 { margin:0; }.timeline-heading > .actions { margin-left:auto; }
.event-count, .hint { color:var(--at-text-muted); font-size:13px; }.hint { line-height:1.5; }
.activity-timeline :deep(.p-timeline-event-opposite) { display:none; }
.activity-timeline :deep(.p-timeline-event-separator) { flex:0 0 32px; width:32px; overflow:visible; }
.activity-timeline :deep(.p-timeline-event-content) { min-width:0; padding:0 0 22px 14px; }
.event-marker { display:flex; align-items:center; justify-content:center; flex:0 0 32px; width:32px; height:32px; border-radius:50%; line-height:1; overflow:visible; }
.event-marker i { display:block; width:1em; height:1em; font-size:14px; line-height:1; }
.event-content { min-width:0; padding-top:3px; }.event-heading { align-items:flex-start; justify-content:space-between; flex-wrap:nowrap; }
.event-heading strong { min-width:0; overflow-wrap:anywhere; font-size:14px; line-height:1.5; font-weight:550; }
.event-heading :deep(button) { flex-shrink:0; }.event-content p { margin:5px 0 0; color:var(--at-text-muted); font-size:12px; line-height:1.5; overflow-wrap:anywhere; }
.entry-form { border-top:1px solid var(--at-border); margin:18px 0; padding-top:18px; }.entry-form fieldset { border:0; margin:0; padding:0; min-width:0; }
.entry-form legend { font-size:14px; font-weight:650; }.entry-form label { display:block; font-size:14px; font-weight:600; margin-top:12px; }.entry-form .actions { margin-top:14px; }
@media(max-width:600px) { .timeline-panel.embedded { padding:0 14px 14px; }.timeline-heading > .actions { margin-left:0; }.activity-timeline :deep(.p-timeline-event-content) { padding-left:10px; } }
</style>
