<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import { getRecipientPage, getRecipientPages, type RecipientPageDetail, type RecipientPageList } from '../../api'
const props = defineProps<{ applicationId?: string; revision?: string }>()
const opened = ref(false)
const pages = ref<RecipientPageList | null>(null)
const detail = ref<RecipientPageDetail | null>(null)
const loading = ref(false)
const error = ref('')
let requestVersion = 0
async function load(page = 1) {
  const version = ++requestVersion
  loading.value = true; error.value = ''; detail.value = null
  try { const value = await getRecipientPages(props.applicationId, page); if (version === requestVersion) pages.value = value }
  catch (reason) { if (version === requestVersion) error.value = reason instanceof Error ? reason.message : 'Unable to load saved reports.' }
  finally { if (version === requestVersion) loading.value = false }
}
async function show(id: string) {
  const version = ++requestVersion
  loading.value = true; error.value = ''
  try { const value = await getRecipientPage(id, props.applicationId); if (version === requestVersion) detail.value = value }
  catch (reason) { if (version === requestVersion) error.value = reason instanceof Error ? reason.message : 'Unable to load this report.' }
  finally { if (version === requestVersion) loading.value = false }
}
function toggle(event: Event) { opened.value = (event.target as HTMLDetailsElement).open; if (opened.value) void load() }
function safeLink(value: string) { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? value : '' } catch { return '' } }
function date(value: string | null) { return value ? new Date(value).toLocaleString() : 'Unknown' }
watch(() => [props.applicationId, props.revision], () => { requestVersion++; pages.value = null; detail.value = null; if (opened.value) void load() })
onUnmounted(() => { requestVersion++ })
</script>

<template>
  <details class="page-reports" @toggle="toggle"><summary>Saved recipient page reports</summary>
    <p>Extracted findings are reused across applications until you request a refresh. A saved report does not confirm employer identity or vacancy responsibility.</p>
    <p v-if="loading" role="status">Loading saved reports…</p><p v-if="error" class="at-message error" role="alert">{{ error }}</p>
    <template v-if="pages"><p>{{ pages.total }} saved page report{{ pages.total === 1 ? '' : 's' }}. Reports older than seven days are marked for review.</p>
      <article v-for="page in pages.items" :key="page.id"><strong>{{ page.title || page.url }}</strong><p><a v-if="safeLink(page.resolved_url || page.url)" :href="safeLink(page.resolved_url || page.url)" target="_blank" rel="noopener noreferrer">{{ page.resolved_url || page.url }}</a></p><p>{{ page.outcome }} · {{ page.candidate_count }} contact records · {{ date(page.fetched_at) }}<span v-if="page.stale"> · Older evidence — review needed</span></p><Button type="button" severity="secondary" :disabled="loading" @click="show(page.id)">Read report</Button></article>
      <div v-if="pages.total > pages.page_size" class="actions"><Button type="button" severity="secondary" :disabled="loading || pages.page === 1" @click="load(pages.page - 1)">Previous reports</Button><span>Page {{ pages.page }} of {{ Math.ceil(pages.total / pages.page_size) }}</span><Button type="button" severity="secondary" :disabled="loading || pages.page * pages.page_size >= pages.total" @click="load(pages.page + 1)">Next reports</Button></div>
    </template>
    <section v-if="detail" class="report" aria-label="Saved page report"><h4>{{ detail.title || detail.url }}</h4><p>{{ detail.report.summary || 'No readable summary was extracted.' }}</p><p v-if="detail.report.error">{{ detail.report.error }}</p><p v-if="detail.report.rendering_signals?.length">Rendering signals: {{ detail.report.rendering_signals.join(', ') }}</p><ul><li v-for="(contact, index) in detail.report.candidates" :key="index">{{ [contact.name, contact.role, contact.email, contact.purpose].filter(Boolean).join(' · ') }}<span v-if="contact.exclusion_reason"> · Excluded: {{ contact.exclusion_reason }}</span></li></ul><p>{{ detail.report.contact_links.length }} related links saved for further research.</p></section>
  </details>
</template>

<style scoped>
.page-reports{margin-top:18px;padding:12px;border:1px solid var(--at-border);border-radius:6px}summary{cursor:pointer;font-weight:600}article{border-top:1px solid var(--at-border);padding:12px 0}p,li{overflow-wrap:anywhere}.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.report{padding:12px;background:var(--at-background);border-radius:6px}
</style>
