<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createInterview, deleteInterview, listApplicationInterviews, updateInterview, type Interview, type InterviewInput, type InterviewType } from './api'
import { dateTimeText, interviewTypeText, relativeDateText } from './dateText'

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ changed: [] }>()
const types: InterviewType[] = ['PHONE', 'HR', 'TECHNICAL', 'ONSITE', 'FINAL', 'OTHER']
const interviews = ref<Interview[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const open = ref(false)
const editingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)

function blankForm() {
  return { type: 'TECHNICAL' as InterviewType, scheduled_at: '', duration: null as number | null, location: '', meeting_url: '', interviewer: '', email_reference: '', notes: '', result: '' }
}
const form = reactive(blankForm())

function localDateTime(value: string) {
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

async function load() {
  busy.value = true; error.value = ''
  try { interviews.value = await listApplicationInterviews(props.applicationId) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load interviews.' }
  finally { busy.value = false }
}

function add() {
  Object.assign(form, blankForm()); editingId.value = null; deletingId.value = null; open.value = true; error.value = ''; notice.value = ''
}

function edit(item: Interview) {
  Object.assign(form, {
    type: item.type, scheduled_at: localDateTime(item.scheduled_at), duration: item.duration,
    location: item.location ?? '', meeting_url: item.meeting_url ?? '', interviewer: item.interviewer ?? '',
    email_reference: item.email_reference ?? '', notes: item.notes ?? '', result: item.result ?? '',
  })
  editingId.value = item.id; deletingId.value = null; open.value = true; error.value = ''; notice.value = ''
}

function payload(): InterviewInput {
  return {
    type: form.type, scheduled_at: new Date(form.scheduled_at).toISOString(), duration: form.duration || null,
    location: form.location.trim() || null, meeting_url: form.meeting_url.trim() || null,
    interviewer: form.interviewer.trim() || null, email_reference: form.email_reference.trim() || null,
    notes: form.notes.trim() || null, result: form.result.trim() || null,
  }
}

async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const saved = editingId.value
      ? await updateInterview(props.applicationId, editingId.value, payload())
      : await createInterview(props.applicationId, payload())
    interviews.value = editingId.value ? interviews.value.map(item => item.id === saved.id ? saved : item) : [...interviews.value, saved]
    interviews.value.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at) || a.id.localeCompare(b.id))
    notice.value = editingId.value ? 'Interview updated.' : 'Interview added.'
    emit('changed')
    open.value = false; editingId.value = null
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to save interview.' }
  finally { busy.value = false }
}

async function remove(item: Interview) {
  if (deletingId.value !== item.id) { deletingId.value = item.id; return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await deleteInterview(props.applicationId, item.id)
    interviews.value = interviews.value.filter(row => row.id !== item.id)
    deletingId.value = null; notice.value = 'Interview deleted.'
    emit('changed')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to delete interview.' }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <section class="panel interview-panel" aria-labelledby="application-interviews-title">
    <div class="section-heading"><h3 id="application-interviews-title">Interviews <span>{{ interviews.length }}</span></h3><button v-if="!open" type="button" :disabled="busy" @click="add">Add interview</button></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <form v-if="open" @submit.prevent="save"><fieldset :disabled="busy"><legend>{{ editingId ? 'Edit interview' : 'New interview' }}</legend>
      <div class="grid"><label>Type<select v-model="form.type"><option v-for="type in types" :key="type" :value="type">{{ interviewTypeText(type) }}</option></select></label><label>Scheduled (local time)<input v-model="form.scheduled_at" type="datetime-local" required /></label><label>Duration (minutes)<input v-model.number="form.duration" type="number" min="1" max="1440" /></label><label>Interviewer<input v-model="form.interviewer" maxlength="300" /></label><label>Location<input v-model="form.location" maxlength="300" /></label><label>Meeting URL<input v-model="form.meeting_url" type="url" maxlength="2048" /></label><label>Email reference<input v-model="form.email_reference" maxlength="2048" /></label></div>
      <label>Preparation notes<textarea v-model="form.notes" rows="3"></textarea></label><label>Result<textarea v-model="form.result" rows="3"></textarea></label>
      <div class="actions"><button class="primary" type="submit">{{ busy ? 'Saving…' : 'Save interview' }}</button><button type="button" @click="open = false">Cancel</button></div>
    </fieldset></form>
    <p v-if="busy && !interviews.length && !open" role="status">Loading interviews…</p><p v-else-if="!interviews.length && !open" class="muted">No interviews scheduled.</p>
    <article v-for="item in interviews" :key="item.id" class="interview-item">
      <div class="section-heading"><div><strong>{{ interviewTypeText(item.type) }} interview — {{ relativeDateText(item.scheduled_at) }}</strong><p class="meta">{{ dateTimeText(item.scheduled_at) }}<template v-if="item.duration"> · {{ item.duration }} minutes</template></p></div><div class="actions"><button type="button" :disabled="busy" @click="edit(item)">Edit</button><button type="button" :disabled="busy" :class="{ danger: deletingId === item.id }" @click="remove(item)">{{ deletingId === item.id ? 'Confirm delete' : 'Delete' }}</button></div></div>
      <p v-if="item.interviewer || item.location" class="meta"><template v-if="item.interviewer">With {{ item.interviewer }}</template><template v-if="item.interviewer && item.location"> · </template>{{ item.location }}</p>
      <p v-if="item.notes" class="content">{{ item.notes }}</p><p v-if="item.result" class="result"><strong>Result:</strong> {{ item.result }}</p>
      <p><a v-if="item.meeting_url" :href="item.meeting_url" target="_blank" rel="noopener noreferrer">Open meeting link ↗</a><span v-if="item.meeting_url && item.email_reference"> · </span><span v-if="item.email_reference">Email: {{ item.email_reference }}</span></p>
    </article>
  </section>
</template>

<style scoped>
.interview-panel { margin-top: 32px; } .section-heading, .actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h3 span { color: #627084; font-size: 13px; font-weight: 400; } .interview-item { border-top: 1px solid #e5e9ee; margin-top: 18px; padding-top: 18px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; } fieldset { border: 0; padding: 0; margin: 20px 0; min-width: 0; } legend { font-size: 14px; font-weight: 650; }
label { display: block; font-size: 14px; margin: 12px 0; font-weight: 600; } input, select, textarea { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid #b9c4d2; border-radius: 5px; font: inherit; font-weight: 400; background: #fff; color: #202c3d; } textarea { resize: vertical; }
.meta, .muted { color: #576678; font-size: 13px; line-height: 1.6; margin: 5px 0; } .content, .result { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.6; }
.notice { color: #216344; font-size: 14px; } .primary { background: #263e5c; color: #fff; border-color: #263e5c; } .danger { color: #a12c32; border-color: #a12c32; } a { color: #24568b; }
@media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
</style>
