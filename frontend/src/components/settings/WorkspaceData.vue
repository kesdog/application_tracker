<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import { listApplications, type Application } from '../../api'
import { applyImport, decideMailReview, downloadBackup, getMailReviews, getTrash, previewImport, previewMerge, mergeApplications,
  restoreApplication, validateRecovery, type ImportPreview, type MailReview, type MergePreview } from '../../workspaceApi'
import Pagination from '../../Pagination.vue'

const busy = ref(false), error = ref(''), message = ref('')
const file = ref<File>(), preview = ref<ImportPreview>(), selected = ref<number[]>([]), duplicates = ref('skip'), dirty = ref(false)
const importPage = ref(1), trashPage = ref(1), reviewPage = ref(1)
const trash = ref<{ total: number; items: Application[] }>({ total: 0, items: [] })
const reviews = ref<{ total: number; items: MailReview[] }>({ total: 0, items: [] })
const applications = ref<Application[]>([]), chosen = ref<Record<string, string>>({})
const reply = ref<Record<string, boolean>>({}), reminder = ref<Record<string, string>>({})
const newApplication = ref<Record<string, { company: string; job_title: string; date_applied: string }>>({})
const mergeSource = ref(''), mergeTarget = ref(''), mergePlan = ref<MergePreview>(), mergeFields = ref<string[]>([]), mergeConfirmed = ref(false)
async function inspectMerge() { mergePlan.value = await previewMerge(mergeSource.value, mergeTarget.value); mergeFields.value = []; mergeConfirmed.value = false }
async function saveMerge() { if (!mergePlan.value || !mergeConfirmed.value) return; await mergeApplications(mergePlan.value, mergeFields.value); mergePlan.value = undefined; mergeSource.value = ''; mergeTarget.value = ''; applications.value = await listApplications(); message.value = 'Applications consolidated. Review archived follow-ups before resuming reminders.'; window.dispatchEvent(new Event('tracker:invalidate')) }
const visibleRows = computed(() => preview.value?.rows.slice((importPage.value - 1) * 20, importPage.value * 20) ?? [])
async function perform(action: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await action() } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to complete this action.' }
  finally { busy.value = false }
}
function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]; preview.value = undefined; selected.value = []; dirty.value = false
}
async function inspect() {
  if (!file.value) return
  const result = await previewImport(file.value, preview.value?.mapping)
  preview.value = result; selected.value = result.rows.filter(row => !row.errors.length).map(row => row.row)
  importPage.value = 1; dirty.value = false
}
async function saveImport() {
  if (!file.value || !preview.value || dirty.value) return
  const result = await applyImport(file.value, preview.value.mapping, selected.value, duplicates.value)
  message.value = `${result.created.length} ${result.created.length === 1 ? 'application' : 'applications'} imported; ${result.skipped} ${result.skipped === 1 ? 'duplicate' : 'duplicates'} skipped.`
  preview.value = undefined; selected.value = []; window.dispatchEvent(new Event('tracker:invalidate'))
}
async function loadTrash() { trash.value = await getTrash(trashPage.value) }
async function loadReviews() {
  const [page, records] = await Promise.all([getMailReviews(reviewPage.value), listApplications()])
  reviews.value = page; applications.value = records
  for (const item of page.items) {
    newApplication.value[item.message_id] ??= { company: '', job_title: '', date_applied: '' }
    reminder.value[item.message_id] ??= 'keep'
    chosen.value[item.message_id] ??= item.application_id || ''
  }
}
async function decide(item: MailReview, action: 'ignore' | 'link' | 'create') {
  const parent = applications.value.find(record => record.id === chosen.value[item.message_id])
  await decideMailReview(item.message_id, { action, application_id: parent?.id, expected_revision: parent?.revision,
    ...(action === 'create' ? { application: { ...newApplication.value[item.message_id], email_reference: item.url } } : {}),
    employer_reply: Boolean(reply.value[item.message_id]), followups: reminder.value[item.message_id] || 'keep' })
  await loadReviews(); window.dispatchEvent(new Event('tracker:invalidate')); message.value = 'Email review saved.'
}
function whenOpened(event: Event, action: () => Promise<unknown>) { if ((event.target as HTMLDetailsElement).open) void perform(action) }
</script>
<template>
  <section class="panel workspace-data" aria-labelledby="workspace-data-title" :aria-busy="busy">
    <h3 id="workspace-data-title">Data &amp; recovery</h3>
    <p>Bring existing records into your workspace, review imported emails, and keep a complete recovery copy.</p>
    <p v-if="error" role="alert" class="at-message error">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <details><summary>Import a spreadsheet</summary>
      <p>Choose CSV or XLSX (up to 10 MiB and 5,000 rows). Review columns and selected rows before saving. Dates use YYYY-MM-DD. Formula cells must be replaced with values.</p>
      <label>Spreadsheet<input type="file" accept=".csv,.xlsx" :disabled="busy" @change="chooseFile" /></label>
      <Button type="button" :disabled="busy || !file" @click="perform(inspect)">Preview import</Button>
      <template v-if="preview">
        <div class="mapping"><label v-for="header in preview.headers" :key="header">{{ header }}<select v-model="preview.mapping[header]" :disabled="busy" @change="dirty = true"><option value="">Ignore column</option><option v-for="field in preview.fields" :key="field" :value="field">{{ field.replaceAll('_', ' ') }}</option></select></label></div>
        <p v-if="dirty">Column mapping changed. Preview again before importing.</p>
        <div class="table-scroll"><table><thead><tr><th>Import</th><th>Row</th><th>Company / role</th><th>Review</th></tr></thead><tbody><tr v-for="row in visibleRows" :key="row.row"><td><input v-model="selected" type="checkbox" :value="row.row" :disabled="busy || Boolean(row.errors.length)" :aria-label="`Import row ${row.row}`" /></td><td>{{ row.row }}</td><td>{{ row.application.company }} · {{ row.application.job_title }}</td><td>{{ row.errors.join('; ') || (row.duplicates.length ? 'Possible duplicate' : 'Ready') }}</td></tr></tbody></table></div>
        <Pagination v-model:page="importPage" :total="preview.rows.length" :page-size="20" label="import rows" />
        <label>Possible duplicates<select v-model="duplicates" :disabled="busy"><option value="skip">Skip matching existing applications</option><option value="create">Create another application after review</option></select></label>
        <Button type="button" :disabled="busy || dirty || !selected.length" @click="perform(saveImport)">Import {{ selected.length }} selected rows</Button>
      </template>
    </details>
    <details @toggle="whenOpened($event, loadReviews)"><summary>Review imported emails</summary>
      <p>Read the original email, choose its application, and decide what should happen to existing reminders. Linking never changes the application outcome.</p>
      <p v-if="!reviews.total">No emails awaiting review for the connected account.</p>
      <article v-for="item in reviews.items" :key="item.message_id" class="review-item">
        <a :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.subject }}</a><p>{{ item.reason }}</p>
        <label>Application<select v-model="chosen[item.message_id]" :disabled="busy"><option value="">Choose application</option><option v-for="record in applications" :key="record.id" :value="record.id">{{ record.company }} · {{ record.job_title }} · {{ record.date_applied }}</option></select></label>
        <a v-if="chosen[item.message_id]" :href="`#/applications/${chosen[item.message_id]}`" target="_blank" rel="noopener noreferrer">Review selected application</a>
        <label><input v-model="reply[item.message_id]" type="checkbox" :disabled="busy" /> This is an employer reply</label>
        <label>Existing follow-ups<select v-model="reminder[item.message_id]" :disabled="busy"><option value="keep">Keep current reminders</option><option value="pause">Pause job reminders</option><option value="archive">Archive unsent follow-ups</option></select></label>
        <div class="actions"><Button type="button" :disabled="busy || !chosen[item.message_id]" @click="perform(() => decide(item, 'link'))">Link after review</Button><Button type="button" severity="secondary" :disabled="busy" @click="perform(() => decide(item, 'ignore'))">Dismiss email</Button></div>
        <details><summary>Create an application from this email</summary><template v-if="newApplication[item.message_id]"><label>Company<input v-model="newApplication[item.message_id]!.company" :disabled="busy" /></label><label>Job title<input v-model="newApplication[item.message_id]!.job_title" :disabled="busy" /></label><label>Applied date<input v-model="newApplication[item.message_id]!.date_applied" type="date" :disabled="busy" /></label><Button type="button" :disabled="busy || !newApplication[item.message_id]!.company || !newApplication[item.message_id]!.job_title || !newApplication[item.message_id]!.date_applied" @click="perform(() => decide(item, 'create'))">Create after review</Button></template></details>
      </article>
      <Pagination v-model:page="reviewPage" :total="reviews.total" :page-size="20" label="emails needing review" @update:page="perform(loadReviews)" />
    </details>
    <details @toggle="whenOpened($event, async () => { applications = await listApplications() })"><summary>Consolidate duplicate applications</summary>
      <p>Keep one application and choose which details to take from the duplicate. Original work and audit history remain in Trash; copies of notes, tasks, interviews, documents and follow-ups appear on the kept application. Copied unsent follow-ups are archived and reminders are paused for review.</p>
      <label>Keep application<select v-model="mergeTarget" :disabled="busy" @change="mergePlan = undefined"><option value="">Choose application</option><option v-for="item in applications" :key="item.id" :value="item.id">{{ item.company }} · {{ item.job_title }} · {{ item.date_applied }}</option></select></label>
      <label>Duplicate application<select v-model="mergeSource" :disabled="busy" @change="mergePlan = undefined"><option value="">Choose duplicate</option><option v-for="item in applications.filter(item => item.id !== mergeTarget)" :key="item.id" :value="item.id">{{ item.company }} · {{ item.job_title }} · {{ item.date_applied }}</option></select></label>
      <Button type="button" :disabled="busy || !mergeTarget || !mergeSource || mergeTarget === mergeSource" @click="perform(inspectMerge)">Review consolidation</Button>
      <template v-if="mergePlan"><div class="table-scroll"><table><thead><tr><th>Take duplicate value</th><th>Field</th><th>Kept value</th><th>Duplicate value</th></tr></thead><tbody><tr v-for="field in mergePlan.fields" :key="field"><td><input v-model="mergeFields" :value="field" type="checkbox" :aria-label="`Use duplicate ${field}`" :disabled="busy" @change="mergeConfirmed = false" /></td><td>{{ field.replaceAll('_', ' ') }}</td><td>{{ mergePlan.target[field as keyof Application] ?? 'Empty' }}</td><td>{{ mergePlan.source[field as keyof Application] ?? 'Empty' }}</td></tr></tbody></table></div><p>Work copied: {{ Object.entries(mergePlan.counts).map(([kind, count]) => `${count} ${kind.replaceAll('_', ' ')}`).join(' · ') }}.</p><p>Restoring the original from Trash will also restore its original work, which may then duplicate the copies.</p><label><input v-model="mergeConfirmed" type="checkbox" :disabled="busy" /> I reviewed both applications and the field choices.</label><Button type="button" :disabled="busy || !mergeConfirmed" @click="perform(saveMerge)">Consolidate reviewed applications</Button></template>
    </details>
    <details @toggle="whenOpened($event, loadTrash)"><summary>Deleted applications</summary><p>Restore applications with their history and documents. Reminders stay paused until you review and resume them.</p>
      <p v-if="!trash.total">No deleted applications.</p><ul><li v-for="item in trash.items" :key="item.id">{{ item.company }} · {{ item.job_title }} <Button type="button" severity="secondary" :disabled="busy" @click="perform(async () => { await restoreApplication(item); await loadTrash(); message = 'Application restored with reminders paused.'; })">Restore</Button></li></ul>
      <Pagination v-model:page="trashPage" :total="trash.total" :page-size="20" label="deleted applications" @update:page="perform(loadTrash)" />
    </details>
    <details><summary>Back up and verify recovery</summary><p>A full backup includes your records and uploaded documents. Keep it private and store a copy away from this device. Google credentials and recovery keys need their separate recovery process.</p>
      <Button type="button" :disabled="busy" @click="perform(async () => { await downloadBackup(); message = 'Backup downloaded. Keep an off-device copy.' })">Download full backup</Button>
      <label>Verify a backup ZIP<input type="file" accept=".zip" :disabled="busy" @change="(event) => { const selectedFile = (event.target as HTMLInputElement).files?.[0]; if (selectedFile) perform(async () => { const result = await validateRecovery(selectedFile); message = `${result.message} ${result.applications} applications.` }) }" /></label>
      <p>Verification restores an isolated temporary copy. To recover your installation, stop the tracker, extract the ZIP, and use the documented recovery command with a new empty data directory. Your open workspace is never overwritten.</p>
    </details>
  </section>
</template>
<style scoped>
.workspace-data { background:var(--at-surface); border:1px solid var(--at-border); border-radius:8px; padding:24px; margin:20px 0; overflow-wrap:anywhere; }
p { color:var(--at-text-muted); line-height:1.6; } details { border-top:1px solid var(--at-border); padding:16px 0; } summary { cursor:pointer; font-weight:650; } label { display:flex; flex-direction:column; gap:6px; margin:12px 0; } label:has(input[type=checkbox]) { flex-direction:row; align-items:center; } select, input:not([type=checkbox]) { width:100%; padding:10px; border:1px solid var(--at-border); border-radius:6px; background:var(--at-surface); color:var(--at-text); font:inherit; } .mapping { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; } .actions { display:flex; flex-wrap:wrap; gap:10px; }.table-scroll { overflow:auto; } table { width:100%; text-align:left; }th,td { padding:10px; border-bottom:1px solid var(--at-border); }.review-item { margin:16px 0; padding:12px; border:1px solid var(--at-border); border-radius:8px; }li { margin:12px 0; }@media(max-width:480px) { .workspace-data { padding:14px; } }
</style>
