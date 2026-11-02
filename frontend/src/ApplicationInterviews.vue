<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import Select from 'primevue/select'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import DateTimeField from './components/shared/DateTimeField.vue'
import NumberField from './components/shared/NumberField.vue'
import InputText from 'primevue/inputtext'
import { onMounted, reactive, ref } from 'vue'
import { createInterview, deleteInterview, listApplicationInterviews, updateInterview, type Interview, type InterviewInput, type InterviewType } from './api'
import { dateTimeText, interviewTypeText, relativeDateText } from './dateText'
import EmailReference from './EmailReference.vue'
import { useConfirm } from 'primevue/useconfirm'
import { interviewTypeMeta, interviewTypeOptions } from './presentation/interviewPresentation'
import AppTag from './components/shared/AppTag.vue'

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ changed: [] }>()
const interviews = ref<Interview[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const open = ref(false)
const editingId = ref<string | null>(null)
const confirm = useConfirm()

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
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to load interviews.") }
  finally { busy.value = false }
}

function add() {
  Object.assign(form, blankForm()); editingId.value = null; open.value = true; error.value = ''; notice.value = ''
}

function edit(item: Interview) {
  Object.assign(form, {
    type: item.type, scheduled_at: localDateTime(item.scheduled_at), duration: item.duration,
    location: item.location ?? '', meeting_url: item.meeting_url ?? '', interviewer: item.interviewer ?? '',
    email_reference: item.email_reference ?? '', notes: item.notes ?? '', result: item.result ?? '',
  })
  editingId.value = item.id; open.value = true; error.value = ''; notice.value = ''
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
    notice.value = editingId.value ? t("Interview updated.") : t("Interview added.")
    emit('changed')
    open.value = false; editingId.value = null
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to save interview.") }
  finally { busy.value = false }
}

async function remove(item: Interview) {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await deleteInterview(props.applicationId, item.id)
    interviews.value = interviews.value.filter(row => row.id !== item.id)
    notice.value = t("Interview deleted.")
    emit('changed')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to delete interview.") }
  finally { busy.value = false }
}

function confirmDelete(item: Interview) {
  confirm.require({ get header() { return t("Delete interview?") }, message: t("Delete the {p0} interview on {p1}?", { p0: interviewTypeMeta[item.type].label.toLowerCase(), p1: dateTimeText(item.scheduled_at) }), icon: 'pi pi-exclamation-triangle', rejectProps: { get label() { return t("Keep interview") }, severity: 'secondary', outlined: true }, acceptProps: { get label() { return t("Delete interview") }, severity: 'danger' }, defaultFocus: 'reject', accept: () => { void remove(item) } })
}

onMounted(load)
</script>

<template>
  <section class="panel interview-panel" :aria-label="t('Interviews')">
    <div class="section-heading"><h3 v-if="interviews.length" id="application-interviews-title">{{ t("Interviews") }} <span>{{ interviews.length }}</span></h3><Button v-if="!open" type="button" :disabled="busy" @click="add">{{ t("Add interview") }}</Button></div>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p><p v-if="notice" class="at-message success" role="status">{{ messageText(String((notice) ?? '')) }}</p>
    <form v-if="open" @submit.prevent="save"><fieldset :disabled="busy"><legend>{{ editingId ? t("Edit interview") : t("New interview") }}</legend>
      <div class="grid"><label>{{ t("Type") }}<Select class="at-form-control" :aria-label="t('Type')" v-model="form.type" :disabled="busy" :options="interviewTypeOptions" option-label="label" option-value="value" option-disabled="disabled" /></label><DateTimeField v-model="form.scheduled_at" :label="t('Scheduled (local time)')" :disabled="busy" required /><NumberField v-model="form.duration" :label="t('Duration (minutes)')" :disabled="busy" :min="1" :max="1440" /><label>{{ t("Interviewer") }}<InputText class="at-form-control" v-model="form.interviewer" maxlength="300" /></label><label>{{ t("Location") }}<InputText class="at-form-control" v-model="form.location" maxlength="300" /></label><label>{{ t("Meeting URL") }}<InputText class="at-form-control" v-model="form.meeting_url" type="url" maxlength="2048" /></label><label>{{ t("Email reference") }}<InputText class="at-form-control" v-model="form.email_reference" maxlength="2048" /></label></div>
      <label>{{ t("Preparation notes") }}<Textarea class="at-form-control" v-model="form.notes" rows="3"></Textarea></label><label>{{ t("Result") }}<Textarea class="at-form-control" v-model="form.result" rows="3"></Textarea></label>
      <div class="actions"><Button class="primary" type="submit">{{ busy ? t("Saving…") : t("Save interview") }}</Button><Button type="button" @click="open = false">{{ t("Cancel") }}</Button></div>
    </fieldset></form>
    <p v-if="busy && !interviews.length && !open" role="status">{{ t("Loading interviews…") }}</p>
    <article v-for="item in interviews" :key="item.id" class="interview-item">
      <div class="section-heading"><div><AppTag v-bind="interviewTypeMeta[item.type]" /><strong> {{ t("interview —") }} {{ relativeDateText(item.scheduled_at) }}</strong><p class="meta">{{ dateTimeText(item.scheduled_at) }}<template v-if="item.duration"> · {{ item.duration }} {{ t("minutes") }}</template></p></div><div class="actions"><Button type="button" severity="secondary" outlined :disabled="busy" @click="edit(item)">{{ t("Edit") }}</Button><Button type="button" severity="danger" outlined :disabled="busy" @click="confirmDelete(item)">{{ t("Delete") }}</Button></div></div>
      <p v-if="item.interviewer || item.location" class="meta"><template v-if="item.interviewer">{{ t("With") }} {{ item.interviewer }}</template><template v-if="item.interviewer && item.location"> · </template>{{ item.location }}</p>
      <p v-if="item.notes" class="content">{{ item.notes }}</p><p v-if="item.result" class="result"><strong>{{ t("Result:") }}</strong> {{ item.result }}</p>
      <p v-if="item.meeting_url || item.email_reference"><a v-if="item.meeting_url" :href="item.meeting_url" target="_blank" rel="noopener noreferrer">{{ t("Open meeting link ↗") }}</a><span v-if="item.meeting_url && item.email_reference"> · </span><EmailReference v-if="item.email_reference" :reference="item.email_reference" /></p>
      <p><a :href="`/api/interviews/${encodeURIComponent(item.id)}/calendar.ics`" :download="`interview-${item.id}.ics`">{{ t("Download calendar event") }}</a></p>
    </article>
  </section>
</template>

<style scoped>
@layer legacy {
.interview-panel { margin-top: 32px; } .section-heading, .actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h3 span { color: var(--at-text-muted); font-size: 13px; font-weight: 400; } .interview-item { border-top: 1px solid var(--at-border); margin-top: 18px; padding-top: 18px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; } fieldset { border: 0; padding: 0; margin: 20px 0; min-width: 0; } legend { font-size: 14px; font-weight: 650; }
label { display: block; font-size: 14px; margin: 12px 0; font-weight: 600; } input, select, textarea { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid var(--at-border); border-radius: 5px; font: inherit; font-weight: 400; background: var(--at-surface); color: var(--at-text); } textarea { resize: vertical; }
.meta, .muted { color: var(--at-text-muted); font-size: 13px; line-height: 1.6; margin: 5px 0; } .content, .result { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.6; }
.notice { color: var(--at-successful); font-size: 14px; } .primary { background: var(--at-primary); color:var(--at-primary-contrast); border-color: var(--at-primary); } .danger { color: var(--at-unsuccessful); border-color: var(--at-unsuccessful); } a { color: var(--at-link); }
@media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
}
</style>
