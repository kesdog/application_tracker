<script setup lang="ts">
import Select from 'primevue/select'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import DateTimeField from './components/shared/DateTimeField.vue'
import InputText from 'primevue/inputtext'
import { computed, onMounted, reactive, ref } from 'vue'
import { createFollowUp, createNote, createTask, draftEmailFollowup, getWork, updateFollowUp, updateNote, updateTask, type ApplicationWork, type FollowUp, type FollowUpChannel, type Note, type NoteType, type Task } from './api'
import Pagination from './Pagination.vue'
import AppTag from './components/shared/AppTag.vue'
import { followupStatusMeta, taskStatusMeta, urgencyMeta } from './presentation/taskPresentation'

const props = defineProps<{ applicationId: string; phoneNumber: string | null }>()
const emit = defineEmits<{ changed: [] }>()
const work = ref<ApplicationWork | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const noteTypes: NoteType[] = ['GENERAL', 'ASSESSMENT', 'EMAIL_DRAFT', 'INTERVIEW', 'AGENT']
const noteForm = reactive({ id: '', content: '', type: 'GENERAL' as NoteType })
const taskForm = reactive({ title: '', description: '', due_at: '' })
const followupForm = reactive({ due_at: '', template_reference: '', channel: 'EMAIL' as FollowUpChannel })
const noteOpen = ref(false)
const taskOpen = ref(false)
const followupOpen = ref(false)
const draftingId = ref<string | null>(null)
const draftContent = ref('')
const followupPage = ref(1)
const followupPageSize = 5
const visibleFollowups = computed(() => (work.value?.followups ?? []).slice((followupPage.value - 1) * followupPageSize, followupPage.value * followupPageSize))
const dateText = (value: string | null) => value ? new Date(value).toLocaleString() : 'No date set'
const isoDate = (value: string) => value ? new Date(value).toISOString() : null

async function load() {
  busy.value = true
  error.value = ''
  try { work.value = await getWork(props.applicationId); followupPage.value = 1 }
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
    const item = await createFollowUp(props.applicationId, { due_at: isoDate(followupForm.due_at), template_reference: followupForm.template_reference || null, channel: followupForm.channel })
    work.value!.followups.push(item)
    followupPage.value = Math.ceil(work.value!.followups.length / followupPageSize)
    Object.assign(followupForm, { due_at: '', template_reference: '', channel: 'EMAIL' })
    followupOpen.value = false
  }, 'Follow-up added.')
}

function setFollowupStatus(item: FollowUp, status: FollowUp['status']) {
  return perform(async () => {
    const saved = await updateFollowUp(props.applicationId, item.id, { status })
    work.value!.followups = work.value!.followups.map(row => row.id === saved.id ? saved : row)
  }, 'Follow-up updated. The tracker did not place a call or send email.')
}

async function saveEmailDraft(item: FollowUp) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await draftEmailFollowup(props.applicationId, item.id, draftContent.value)
    work.value = await getWork(props.applicationId)
    notice.value = result.message
    draftingId.value = null; draftContent.value = ''
    emit('changed')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Unable to save the draft.' }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <div class="work" :aria-busy="busy">
    <div class="work-heading"><h3>Application work</h3><Button type="button" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Refresh work' }}</Button></div>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="at-message success" role="status">{{ notice }}</p>
    <p v-if="!work && busy" role="status">Loading notes, tasks, and follow-ups…</p>
    <template v-if="work">
      <div class="actions"><Button v-if="!work.notes.length && !noteOpen" type="button" :disabled="busy" @click="editNote()">Add note</Button><Button v-if="!work.tasks.length && !taskOpen" type="button" :disabled="busy" @click="taskOpen = true">Add task</Button><Button v-if="!work.followups.length && !followupOpen" type="button" :disabled="busy" @click="followupOpen = true">Add follow-up</Button></div>
      <section v-if="work.notes.length || noteOpen" class="panel" aria-labelledby="notes-title">
        <div class="section-heading"><h3 id="notes-title">Notes <span v-if="work.notes.length">{{ work.notes.length }}</span></h3><Button v-if="!noteOpen" type="button" :disabled="busy" @click="editNote()">Add note</Button></div>
        <form v-if="noteOpen" @submit.prevent="saveNote">
          <fieldset :disabled="busy"><legend>{{ noteForm.id ? 'Edit note' : 'New note' }}</legend>
            <label>Note type<Select class="at-form-control" aria-label="Note type" v-model="noteForm.type" :disabled="busy" :options="noteTypes.map(value => ({ value, label: value.replaceAll('_', ' ').toLowerCase() }))" option-label="label" option-value="value" option-disabled="disabled" /></label>
            <label>Note content<Textarea class="at-form-control" v-model="noteForm.content" required rows="4"></Textarea></label>
            <div class="actions"><Button class="primary" type="submit">Save note</Button><Button type="button" @click="noteOpen = false">Cancel note</Button></div>
          </fieldset>
        </form>
        <article v-for="note in work.notes" :key="note.id" class="item">
          <div class="section-heading"><strong v-if="note.type !== 'GENERAL'">{{ note.type }}</strong><Button type="button" :disabled="busy" :aria-label="`Edit ${note.type} note`" @click="editNote(note)">Edit note</Button></div>
          <p class="content">{{ note.content }}</p>
          <p class="meta">{{ note.created_by }} · Created {{ dateText(note.created_at) }} · Updated {{ dateText(note.updated_at) }}</p>
        </article>
      </section>

      <section v-if="work.tasks.length || taskOpen" class="panel" aria-labelledby="tasks-title">
        <div class="section-heading"><h3 id="tasks-title">Tasks <span v-if="work.tasks.length">{{ work.tasks.length }}</span></h3><Button v-if="!taskOpen" type="button" :disabled="busy" @click="taskOpen = true">Add task</Button></div>
        <form v-if="taskOpen" @submit.prevent="saveTask">
          <fieldset :disabled="busy"><legend>New task</legend>
            <label>Task title<InputText class="at-form-control" v-model="taskForm.title" required maxlength="300" /></label>
            <label>Task description<Textarea class="at-form-control" v-model="taskForm.description" rows="3"></Textarea></label>
            <DateTimeField v-model="taskForm.due_at" label="Task due (local time)" :disabled="busy" />
            <div class="actions"><Button class="primary" type="submit">Save task</Button><Button type="button" @click="taskOpen = false">Cancel task</Button></div>
          </fieldset>
        </form>
        <article v-for="task in work.tasks" :key="task.id" class="item" :aria-label="task.title">
          <div class="section-heading"><strong>{{ task.title }}</strong><div class="work-tags"><AppTag v-bind="taskStatusMeta[task.status]" /><AppTag v-if="task.status === 'PENDING' && task.due_at" v-bind="urgencyMeta(task.due_at)" /></div></div>
          <p v-if="task.description" class="content">{{ task.description }}</p>
          <p v-if="task.due_at || task.completed_at" class="meta"><template v-if="task.due_at">Due: {{ dateText(task.due_at) }}</template><template v-if="task.due_at && task.completed_at"> · </template><template v-if="task.completed_at">Completed {{ dateText(task.completed_at) }}</template></p>
          <div class="actions"><Button v-if="task.status !== 'COMPLETED'" type="button" :disabled="busy" @click="setTaskStatus(task, 'COMPLETED')">Complete task</Button><Button v-if="task.status === 'PENDING'" type="button" :disabled="busy" @click="setTaskStatus(task, 'CANCELLED')">Cancel task</Button><Button v-if="task.status !== 'PENDING'" type="button" :disabled="busy" @click="setTaskStatus(task, 'PENDING')">Reopen task</Button></div>
        </article>
      </section>

      <section v-if="work.followups.length || followupOpen" class="panel" aria-labelledby="followups-title">
        <div class="section-heading"><h3 id="followups-title">Follow-ups <span v-if="work.followups.length">{{ work.followups.length }}</span></h3><Button v-if="!followupOpen" type="button" :disabled="busy" @click="followupOpen = true">Add follow-up</Button></div>
        <form v-if="followupOpen" @submit.prevent="saveFollowup">
          <fieldset :disabled="busy"><legend>New follow-up</legend>
            <DateTimeField v-model="followupForm.due_at" label="Follow-up due (local time)" :disabled="busy" />
            <label>Contact by<Select class="at-form-control" aria-label="Contact by" v-model="followupForm.channel" :disabled="busy" :options="[{ value: 'EMAIL', label: 'Email' }, { value: 'PHONE', label: 'Phone call', disabled: !phoneNumber }, { value: 'BOTH', label: 'Email and phone call', disabled: !phoneNumber }]" option-label="label" option-value="value" option-disabled="disabled" /></label>
            <p v-if="!phoneNumber" class="muted">Add a phone number to the application to plan a call.</p>
            <p class="muted">Leave the date blank for {{ work.followup_delay_days }} days from now.</p>
            <label>Template reference<InputText class="at-form-control" v-model="followupForm.template_reference" maxlength="2048" placeholder="Optional name or reference" /></label>
            <div class="actions"><Button class="primary" type="submit">Save follow-up</Button><Button type="button" @click="followupOpen = false">Cancel follow-up</Button></div>
          </fieldset>
        </form>
        <article v-for="item in visibleFollowups" :key="item.id" class="item" :aria-label="`Follow-up ${item.sequence_number}`">
          <div class="section-heading"><strong>{{ item.is_automatic ? 'Automatic ' : '' }}Follow-up #{{ item.sequence_number }} · {{ item.channel === 'BOTH' ? 'Email + phone' : item.channel === 'PHONE' ? 'Phone call' : 'Email' }}</strong><AppTag v-bind="followupStatusMeta[item.status]" :label="item.status === 'SENT' && item.channel !== 'EMAIL' ? 'Completed' : followupStatusMeta[item.status].label" /></div>
          <p class="meta">Due: {{ dateText(item.due_at) }}<template v-if="item.sent_at"> · {{ item.channel === 'EMAIL' ? 'Sent' : 'Completed' }} {{ dateText(item.sent_at) }}</template></p>
          <p v-if="item.template_reference && item.template_reference !== 'Automatic follow-up reminder'" class="content">Template: {{ item.template_reference }}</p>
          <p v-if="item.channel !== 'EMAIL' && phoneNumber" class="meta">Call: <a :href="`tel:${phoneNumber}`">{{ phoneNumber }}</a></p>
          <form v-if="draftingId === item.id" @submit.prevent="saveEmailDraft(item)"><label>Email draft content<Textarea class="at-form-control" v-model="draftContent" required rows="5"></Textarea></label><p class="muted">If mail is not connected, this will be saved as an EMAIL_DRAFT note. It will not be sent.</p><div class="actions"><Button class="primary" type="submit" :disabled="busy">Save draft</Button><Button type="button" @click="draftingId = null">Cancel</Button></div></form>
          <div class="actions"><Button v-if="item.status === 'PENDING' && item.channel !== 'PHONE'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'DRAFTED')">Mark drafted</Button><Button v-if="item.status === 'PENDING' || item.status === 'DRAFTED'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'SENT')">Mark followed up</Button><Button v-if="item.status === 'PENDING' || item.status === 'DRAFTED'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'CANCELLED')">Cancel follow-up</Button><Button v-if="item.status === 'CANCELLED' || item.status === 'SENT'" type="button" :disabled="busy" @click="setFollowupStatus(item, 'PENDING')">Reopen follow-up</Button></div>
          <div v-if="item.channel !== 'PHONE' && (item.status === 'PENDING' || item.status === 'DRAFTED')" class="actions"><Button type="button" :disabled="busy" @click="draftingId = item.id; draftContent = ''">Write email draft</Button></div>
        </article>
        <Pagination v-if="work.followups.length > followupPageSize" v-model:page="followupPage" :total="work.followups.length" :page-size="followupPageSize" label="follow-ups" />
      </section>
    </template>
  </div>
</template>

<style scoped>
@layer legacy {
.work { margin-top: 32px; }
.work-tags { display:flex; flex-wrap:wrap; gap:6px; }
.work-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h3 span { color: var(--at-text-muted); font-size: 13px; font-weight: 400; }
.panel { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; padding: 18px; margin: 16px 0; }
.item { border-top: 1px solid var(--at-border); margin-top: 12px; padding-top: 12px; }
.content { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.6; }
strong { overflow-wrap: anywhere; }
.meta, .muted { color: var(--at-text-muted); font-size: 13px; line-height: 1.6; }
.notice { color: var(--at-successful); font-size: 14px; }
.badge { display: inline-block; background: color-mix(in srgb, var(--at-submitted) 10%, var(--at-surface)); color: var(--at-submitted); font-size: 11px; font-weight: 700; padding: 5px 8px; border-radius: 4px; }
.completed, .sent { color: var(--at-successful); background: color-mix(in srgb, var(--at-successful) 10%, var(--at-surface)); } .cancelled { color: var(--at-text-muted); background: var(--at-surface-muted); }
fieldset { border: 0; margin: 20px 0; padding: 0; min-width: 0; }
legend { font-size: 14px; font-weight: 650; margin-bottom: 10px; }
label { display: block; font-size: 14px; margin: 12px 0; font-weight: 600; }
input, select, textarea { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid var(--at-border); border-radius: 5px; font: inherit; font-weight: 400; background: var(--at-surface); color: var(--at-text); }
textarea { resize: vertical; }
input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid var(--at-focus); outline-offset: 2px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.primary { background: var(--at-primary); color:var(--at-primary-contrast); border-color: var(--at-primary); } .primary:hover:enabled { background: var(--at-primary-hover); }
@media (max-width: 600px) { .panel { padding: 18px; } }
}
</style>
