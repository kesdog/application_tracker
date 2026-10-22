<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import Button from 'primevue/button'
import { getApplicationSync, startApplicationSync, type ApplicationSyncStatus } from '../../api'

const emit = defineEmits<{ changed: [] }>()
const result = ref<ApplicationSyncStatus | null>(null)
const starting = ref(false)
const error = ref('')
const busy = computed(() => starting.value || result.value?.state === 'RUNNING')
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let version = 0
function accept(value: ApplicationSyncStatus, initiated = false) {
  const wasRunning = result.value?.state === 'RUNNING'
  result.value = value
  if (value.state === 'RUNNING') timer = setTimeout(() => void load(), 1000)
  else if ((wasRunning || initiated) && value.state !== 'IDLE') emit('changed')
}
async function load() {
  const current = ++version
  try {
    const value = await getApplicationSync()
    if (disposed || current !== version) return
    error.value = ''
    accept(value)
  } catch {
    if (disposed || current !== version) return
    error.value = 'Could not read sync progress. Your saved applications are kept.'
    if (result.value?.state === 'RUNNING') timer = setTimeout(() => void load(), 2000)
  }
}
async function sync() {
  if (busy.value) return
  clearTimeout(timer)
  const current = ++version
  starting.value = true; error.value = ''
  try {
    const value = await startApplicationSync()
    if (!disposed && current === version) accept(value, true)
  } catch (reason) {
    if (!disposed && current === version) error.value = reason instanceof Error ? reason.message : 'Unable to start sync. Try again.'
  } finally { if (!disposed && current === version) starting.value = false }
}
onMounted(() => void load())
onUnmounted(() => { disposed = true; version++; clearTimeout(timer) })
</script>
<template>
  <div class="application-sync" :aria-busy="busy">
    <Button type="button" severity="secondary" outlined :disabled="busy" @click="sync"><i :class="busy ? 'pi pi-spinner pi-spin' : 'pi pi-sync'" aria-hidden="true" />{{ busy ? 'Syncing…' : 'Sync applications' }}</Button>
    <p v-if="busy" role="status">{{ result?.phase === 'DRIVE' ? 'Synchronizing tracker records with Drive…' : `Checking Gmail for new applications and updates… ${result?.checked ?? 0} emails checked.` }}</p>
    <p v-else-if="result && result.state !== 'IDLE'" role="status">{{ result.created }} new · {{ result.updated }} updated applications · {{ result.checked }} emails checked. {{ result.drive === 'COMPLETED' ? 'Drive synchronized.' : 'Drive sync needs attention.' }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="!busy && result">
      <p v-for="warning in result.warnings" :key="warning" class="warning">{{ warning }}</p>
      <a v-if="result.gmail === 'SETUP_REQUIRED' || result.drive === 'SETUP_REQUIRED' || result.state === 'PARTIAL'" href="#/settings">Open connection & sync settings</a>
      <details v-if="result.review_count"><summary>{{ result.review_count }} {{ result.review_count === 1 ? 'email needs' : 'emails need' }} review</summary><p><a href="#/settings">Resolve emails in Settings → Data &amp; recovery</a></p><ul><li v-for="review in result.reviews ?? []" :key="review.message_id"><a :href="review.url" target="_blank" rel="noopener noreferrer">{{ review.subject }}</a><p>{{ review.reason }}</p></li></ul><p v-if="result.review_count > (result.reviews?.length ?? 0)">Showing the 20 most recent emails needing review.</p></details>
    </template>
  </div>
</template>
<style scoped>
.application-sync { display:flex; flex-direction:column; align-items:flex-end; gap:8px; max-width:620px; min-width:0; }
p { margin:0; font-size:13px; color:var(--at-text-muted); line-height:1.5; }a { font-size:13px; }details { width:100%; }summary { cursor:pointer; font-size:13px; font-weight:600; }ul { padding-left:20px; }li { margin:12px 0; overflow-wrap:anywhere; }
.warning, [role=alert] { color:var(--at-text); border-left:3px solid var(--at-due-soon); padding-left:10px; }
@media(max-width:650px) { .application-sync { align-items:flex-start; width:100%; } }
</style>
