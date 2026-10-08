<script setup lang="ts">
import Select from 'primevue/select'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import { onMounted, reactive, ref } from 'vue'
import { createDocument, documentContentUrl, listDocuments, type ApplicationDocument, type DocumentType } from './api'

const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ changed: [] }>()
const documents = ref<ApplicationDocument[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const form = reactive<{ document_type: DocumentType; filename: string; external_reference: string }>({
  document_type: 'CV', filename: '', external_reference: '',
})

function isWebReference(value: string | null) {
  return Boolean(value && /^https?:\/\//i.test(value))
}

function chooseFile(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
  if (selectedFile.value) form.external_reference = ''
}

function useReference() {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function load() {
  loading.value = true; error.value = ''
  try { documents.value = await listDocuments(props.applicationId) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load documents.' }
  finally { loading.value = false }
}

async function submit() {
  error.value = ''; success.value = ''
  const reference = form.external_reference.trim()
  if (Boolean(selectedFile.value) === Boolean(reference)) {
    error.value = 'Choose one uploaded file or enter one reference.'
    return
  }
  if (reference && !form.filename.trim()) {
    error.value = 'Add a filename for this reference.'
    return
  }
  saving.value = true
  try {
    const saved = await createDocument(props.applicationId, {
      document_type: form.document_type,
      file: selectedFile.value ?? undefined,
      filename: form.filename.trim() || undefined,
      external_reference: reference || undefined,
    })
    await load()
    selectedFile.value = null
    form.filename = ''; form.external_reference = ''
    if (fileInput.value) fileInput.value.value = ''
    success.value = `Attached ${saved.filename}.`
    emit('changed')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Unable to attach document.'
  } finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <section class="panel" aria-label="Documents">
    <div v-if="documents.length" class="section-heading"><h3 id="documents-title">Documents</h3><span>{{ documents.length }}</span></div>
    <details><summary>Attach CV or cover letter</summary>
    <form class="document-form" @submit.prevent="submit">
      <fieldset :disabled="saving">
        <div class="grid">
          <label>Document type<Select class="at-form-control" aria-label="Document type" v-model="form.document_type" :disabled="saving" :options="[{ value: 'CV', label: 'CV' }, { value: 'COVER_LETTER', label: 'Cover letter' }]" option-label="label" option-value="value" option-disabled="disabled" /></label>
          <label>Upload file<input ref="fileInput" type="file" @change="chooseFile" /></label>
          <label>Reference filename<InputText class="at-form-control" v-model="form.filename" maxlength="500" placeholder="cv-product-engineer.pdf" /></label>
          <label>External or local reference<InputText class="at-form-control" v-model="form.external_reference" maxlength="2048" placeholder="https://… or C:\Documents\…" @input="useReference" /></label>
        </div>
        <p class="hint">Choose a file, or enter a reference and its filename. Files are copied into this tracker's data directory.</p>
      </fieldset>
      <Button class="primary" type="submit" :disabled="saving">{{ saving ? 'Attaching…' : 'Attach document' }}</Button>
    </form>
    </details>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p><p v-if="success" class="at-message success" role="status">{{ success }}</p>
    <p v-if="loading && !documents.length" class="empty" role="status">Loading documents…</p>
    <ul v-if="documents.length" class="document-list">
      <li v-for="document in documents" :key="document.id">
        <span class="document-type">{{ document.type === 'CV' ? 'CV' : 'Cover letter' }}</span>
        <div><strong>{{ document.filename }}</strong><p v-if="document.storage_path"><a :href="documentContentUrl(applicationId, document.id)">Download uploaded file</a></p><p v-else-if="isWebReference(document.external_reference)"><a :href="document.external_reference!" target="_blank" rel="noopener noreferrer">Open reference ↗</a></p><p v-else>{{ document.external_reference }}</p></div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
@layer legacy {
summary { cursor:pointer; color:var(--at-link); font-size:14px; font-weight:600; }
.panel { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; padding: 24px; margin: 20px 0; }.section-heading { display: flex; justify-content: space-between; gap: 16px; }.section-heading h3 { margin-bottom: 5px; }.section-heading p, .section-heading span, .hint, .empty { color: var(--at-text-muted); font-size: 13px; }.document-form { border-top: 1px solid var(--at-border); margin-top: 18px; padding-top: 18px; }fieldset { border: 0; padding: 0; margin: 0 0 14px; }.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }label { font-size: 14px; font-weight: 600; }input, select { display: block; width: 100%; min-width: 0; margin-top: 7px; padding: 10px; border: 1px solid var(--at-border); border-radius: 5px; font: inherit; font-weight: 400; background: var(--at-surface); color: var(--at-text); }.primary { background: var(--at-primary); border-color: var(--at-primary); color:var(--at-primary-contrast); }.success { color: var(--at-successful); font-size: 14px; }.document-list { list-style: none; padding: 0; margin: 20px 0 0; }.document-list li { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 14px; border-top: 1px solid var(--at-border); padding: 14px 0; }.document-list p { margin: 5px 0 0; color: var(--at-text-muted); overflow-wrap: anywhere; }.document-type { align-self: start; background: color-mix(in srgb, var(--at-submitted) 10%, var(--at-surface)); color: var(--at-submitted); border-radius: 4px; padding: 5px 7px; font-size: 11px; font-weight: 700; text-align: center; }a { color: var(--at-link); text-underline-offset: 3px; }@media (max-width: 600px) { .grid { grid-template-columns: 1fr; }.panel { padding: 18px; }.document-list li { grid-template-columns: 1fr; }.document-type { justify-self: start; } }
}
</style>
