<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createFollowUp, createNote, createTask, getWork, updateFollowUp, updateNote, updateTask, type ApplicationWork, type FollowUp, type Note, type NoteType, type Task } from './api'

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ changed: [] }>()
const work = ref<ApplicationWork | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const noteTypes: NoteType[] = ['GENERAL', 'ASSESSMENT', 'EMAIL_DRAFT', 'INTERVIEW', 'AGENT']
const noteForm = reactive({ id: '', content: '', type: 'GENERAL' as NoteType })
const taskForm = reactive({ title: '', description: '', due_at: '' })
const followupForm = reactive({ due_at: '', template_reference: '' })
const noteOpen = ref(false)
const taskOpen = ref(false)
const followupOpen = ref(false)
const dateText = (value: string | null) => value ? new Date(value).toLocaleString() : 'No date set'
const isoDate = (value: string) => value ? new Date(value).toISOString() : null

async function load() {
  busy.value = true
  error.value = ''
  try { work.value = await getWork(props.applicationId) }
  catch { error.value = 'Unable to load notes, tasks, and follow-ups. Check the backend and try again.' }
  finally { busy.value = false }
}

async function perform(action: () => Promise<void>, message: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try { await action(); notice.value = message; emit('changed') }
  catch (cause) {
    error.value = cause instanceof TypeError || (cause instanceof Error && cause.name === 'AbortError')
      ? 'Could not confirm the save. Your entries are kept. Refresh work below before retrying to check whether it was saved.'
      : cause instanceof Error ? cause.message : 'Unable to save. Please try again.'
  } finally { busy.value = false }
}

function editNote(note?: Note) {
  Object.assign(noteForm, note ? { id: note.id, content: note.content, type: note.type } : { id: '', content: '', type: 'GENERAL' })
  noteOpen.value = true
}

function saveNote() {
  return perform(async () => {
    const data = { content: noteForm.content, type: noteForm.type }
    const note = noteForm.id ? await updateNote(props.applicationId, noteForm.id, data) : await createNote(props.applicationId, data)
    if (noteForm.id) work.value!.notes = work.value!.notes.map(item => item.id === note.id ? note : item)
    else work.value!.notes.unshift(note)
    noteOpen.value = false
    Object.assign(noteForm, { id: '', content: '', type: 'GENERAL' })
  }, 'Note saved.')
}

function saveTask() {
  return perform(async () => {
    const task = await createTask(props.applicationId, { title: taskForm.title, description: taskForm.description || null, due_at: isoDate(taskForm.due_at) })
    work.value!.tasks.push(task)
    work.value!.tasks.sort((a, b) => (a.due_at ?? '9999').localeCompare(b.due_at ?? '9999'))
    Object.assign(taskForm, { title: '', description: '', due_at: '' })
    taskOpen.value = false
  }, 'Task added.')
}

function setTaskStatus(task: Task, status: Task['status']) {
  return perform(async () => {
    const saved = await updateTask(props.applicationId, task.id, { status })
    work.value!.tasks = work.value!.tasks.map(item => item.id === saved.id ? saved : item)
  }, 'Task updated.')
}

function saveFollowup() {
  return perform(async () => {
    const item = await createFollowUp(props.applicationId, { due_at: isoDate(followupForm.due_at), template_reference: followupForm.template_reference || null })
    work.value!.followups.push(item)
    Object.assign(followupForm, { due_at: '', template_reference: '' })
    followupOpen.value = false
  }, 'Follow-up added.')
}

function setFollowupStatus(item: FollowUp, status: FollowUp['status']) {
  return perform(async () => {
    const saved = await updateFollowUp(props.applicationId, item.id, { status })
    work.value!.followups = work.value!.followups.map(row => row.id === saved.id ? saved : row)
  }, 'Follow-up updated. No email was sent by the tracker.')
}

onMounted(load)
</script>

<template>
  <div class="work" :aria-busy="busy">
    <div class="work-heading"><h3>Application work</h3><button type="button" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Refresh work' }}</button></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="!work && busy" role="status">Loading notes, tasks, and follow-ups…</p>
    <template v-if="work">
      <section class="panel" aria-labelledby="notes-title">
        <div class="section-heading"><h3 id="notes-title">Notes <span>{{ work.notes.length }}</span></h3><button v-if="!noteOpen" type="button" :disabled="busy" @click="editNote()">Add note</button></div>
        <form v-if="noteOpen" @submit.prevent="saveNote">
          <fieldset :disabled="busy"><legend>{{ noteForm.id ? 'Edit note' : 'New note' }}</legend>
            <label>Note type<select v-model="noteForm.type"><option v-for="type in noteTypes" :key="type" :value="type">{{ type }}</option></select></label>
            <label>Note content<textarea v-model="noteForm.content" required rows="4"></textarea></label>
            <div class="actions"><button class="primary" type="submit">Save note</button><button type="button" @click="noteOpen = false">Cancel note</button></div>
          </fieldset>
        </form>
        <p v-if="!work.notes.length" class="muted">No notes yet.</p>
        <article v-for="note in work.notes" :key="note.id" class="item">
          <div class="section-heading"><strong>{{ note.type }}</strong><button type="button" :disabled="busy" :aria-label="`Edit ${note.type} note`" @click="editNote(note)">Edit note</button></div>
          <p class="content">{{ note.content }}</p>
          <p class="meta">{{ note.created_by }} · Created {{ dateText(note.created_at) }} · Updated {{ dateText(note.updated_at) }}</p>
        </article>
      </section>

      <section class="panel" aria-labelledby="tasks-title">
        <div class="section-heading"><h3 id="tasks-title">Tasks <span>{{ work.tasks.length }}</span></h3><button v-if="!taskOpen" type="button" :disabled="busy" @click="taskOpen = true">Add task</button></div>
        <form v-if="taskOpen" @submit.prevent="saveTask">
          <fieldset :disabled="busy"><legend>New task</legend>
            <label>Task title<input v-model="taskForm.title" required maxlength="300" /></label>
            <label>Task description<textarea v-model="taskForm.description" rows="3"></textarea></label>
            <label>Task due (local time)<input v-model="taskForm.due_at" type="datetime-local" /></label>
            <div class="actions"><button class="primary" type="submit">Save task</button><button type="button" @click="taskOpen = false">Cancel task</button></div>
          </fieldset>
        </form>
        <p v-if="!work.tasks.length" class="muted">No tasks yet.</p>
        <article v-for="task in work.tasks" :key="task.id" class="item" :aria-label="task.title">
          <div class="section-heading"><strong>{{ task.title }}</strong><span class="badge" :class="task.status.toLowerCase()">{{ task.status }}</span></div>
          <p v-if="task.description" class="content">{{ task.description }}</p>
          <p class="meta">Due: {{ dateText(task.due_at) }}<template v-if="task.completed_at"> · Completed {{ dateText(task.completed_at) }}</template></p>
          <div class="actions"><button v-if="task.status !== 'COMPLETED'" type="button" :disabled="busy" @click="setTaskStatus(task, 'COMPLETED')">Complete task</button><button v-if="task.status === 'PENDING'" type="button" :disabled="busy" @click="setTaskStatus(task, 'CANCELLED')">Cancel task</button><button v-if="task.status !== 'PENDING'" type="button" :disabled="busy" @click="setTaskStatus(task, 'PENDING')">Reopen task</button></div>
        </article>
      </section>

      <section class="panel" aria-labelledby="followups-title">
        <div class="section-heading"><h3 id="followups-title">Follow-ups <span>{{ work.followups.length }}</span></h3><button v-if="!followupOpen" type="button" :disabled="busy" @click="followupOpen = true">Add follow-up</button></div>
        <p class="muted">Default delay: {{ work.followup_delay_days }} days. Automatic suggestion limit: {{ work.max_followup_suggestions }}. You can add as many manual follow-ups as needed.</p>
        <p class="muted">These are tracking records. Marking drafted or sent does not create or send email.</p>
        <form v-if="followupOpen" @submit.prevent="saveFollowup">
          <fieldset :disabled="busy"><legend>New follow-up</legend>
            <label>Follow-up due (local time)<input v-model="followupForm.due_at" type="datetime-local" /></label>
            <p class="muted">Leave the date blank for {{ work.followup_delay_days }} days from now.</p>
            <label>Template reference<input v-model="followupForm.template_reference" maxlength="2048" placeholder="Optional name or reference" /></label>
            <div class="actions"><button class="primary" type="submit">Save follow-up</button><button type="button" @click="followupOpen = false">Cancel follow-up</button></div>
          </fieldset>
        </form>
        <p v-if="!work.followups.length" class="muted">No follow-ups yet.</p>
        <article v-for="item in work.followups" :key="item.id" class="item" :aria-label="`Follow-up ${item.sequence_number}`">
          <div class="section-heading"><strong>Follow-up #{{ item.sequence_number }}</strong><span class="badge" :class="item.status.toLowerCase()">{{ item.status }}</span></div>
          <p class="meta">Due: {{ dateText(item.due_at) }}<template v-if="item.sent_at"> · Sent {{ dateText(item.sent_at) }}</template></p>
          <p v-if="item.template_reference" class="content">Template: {{ item.template_reference }}</p>
          <div class="actions"><button v-if="item.status === 'PENDING'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'DRAFTED')">Mark drafted</button><button v-if="item.status === 'PENDING' || item.status === 'DRAFTED'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'SENT')">Mark sent</button><button v-if="item.status === 'PENDING' || item.status === 'DRAFTED'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'CANCELLED')">Cancel follow-up</button><button v-if="item.status === 'CANCELLED' || item.status === 'SENT'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'PENDING')">Reopen follow-up</button></div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.work { margin-top: 32px; }
.work-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h3 span { color: #627084; font-size: 13px; font-weight: 400; }
.panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 24px; margin: 20px 0; }
.item { border-top: 1px solid #e5e9ee; margin-top: 18px; padding-top: 18px; }
.content { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.6; }
strong { overflow-wrap: anywhere; }
.meta, .muted { color: #576678; font-size: 13px; line-height: 1.6; }
.notice { color: #216344; font-size: 14px; }
.badge { display: inline-block; background: #eaf1fc; color: #2a5189; font-size: 11px; font-weight: 700; padding: 5px 8px; border-radius: 4px; }
.completed, .sent { color: #216344; background: #eaf5ee; } .cancelled { color: #526174; background: #edf0f3; }
fieldset { border: 0; margin: 20px 0; padding: 0; min-width: 0; }
legend { font-size: 14px; font-weight: 650; margin-bottom: 10px; }
label { display: block; font-size: 14px; margin: 12px 0; font-weight: 600; }
input, select, textarea { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid #b9c4d2; border-radius: 5px; font: inherit; font-weight: 400; background: #fff; color: #202c3d; }
textarea { resize: vertical; }
input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid #527ba8; outline-offset: 2px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.primary { background: #263e5c; color: #fff; border-color: #263e5c; } .primary:hover:enabled { background: #192d45; }
@media (max-width: 600px) { .panel { padding: 18px; } }
</style>
