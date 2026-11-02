<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import PageTabs from './components/shared/PageTabs.vue'
import Button from 'primevue/button'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { listInterviews, type InterviewListItem } from './api'
import { dateTimeText, interviewTypeText, relativeDateText } from './dateText'
import Pagination from './Pagination.vue'
import AppTag from './components/shared/AppTag.vue'
import { interviewTypeMeta } from './presentation/interviewPresentation'

const interviews = ref<InterviewListItem[]>([])
const loading = ref(false)
const error = ref('')
const upcomingPage = ref(1)
const previousPage = ref(1)
const pageSize = 9
const upcoming = computed(() => interviews.value.filter(item => new Date(item.scheduled_at).getTime() >= Date.now()))
const previous = computed(() => interviews.value.filter(item => new Date(item.scheduled_at).getTime() < Date.now()).reverse())
const visibleUpcoming = computed(() => upcoming.value.slice((upcomingPage.value - 1) * pageSize, upcomingPage.value * pageSize))
const visiblePrevious = computed(() => previous.value.slice((previousPage.value - 1) * pageSize, previousPage.value * pageSize))

async function load() {
  loading.value = true
  error.value = ''
  try { interviews.value = await listInterviews(); upcomingPage.value = 1; previousPage.value = 1 }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to load interviews.") }
  finally { loading.value = false }
}

const onInvalidation = () => { void load() }
onMounted(() => { void load(); window.addEventListener('tracker:invalidate', onInvalidation) })
onUnmounted(() => window.removeEventListener('tracker:invalidate', onInvalidation))
</script>

<template>
  <section aria-labelledby="interviews-title">
    <div class="page-heading"><div><h2 id="interviews-title">{{ t("Interviews") }}</h2></div><Button type="button" :disabled="loading" @click="load">{{ loading ? t("Loading…") : t("Refresh") }}</Button></div>
    <p class="intro">{{ t("Prepare for scheduled conversations across all applications.") }}</p>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <p v-if="loading && !interviews.length" role="status">{{ t("Loading interviews…") }}</p>
    <div v-else-if="!interviews.length" class="empty-panel">{{ t("No interviews scheduled. Add one from an application.") }}</div>
    <template v-else>
      <PageTabs :label="t('Interviews views')" :tabs="[{ value: 'current', get label() { return t('Upcoming') }, count: upcoming.length }, { value: 'history', get label() { return t('Previous') }, count: previous.length }]">
      <template #current><p v-if="!upcoming.length" class="empty-panel">{{ t("Nothing upcoming right now.") }}</p>

      <div class="cards">
        <article v-for="item in visibleUpcoming" :key="item.id" class="work-card upcoming">
          <p class="due"><AppTag v-bind="interviewTypeMeta[item.type]" /> {{ t("interview —") }} {{ relativeDateText(item.scheduled_at) }}</p>
          <h3><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a></h3>
          <p class="company">{{ item.application.company }}</p>
          <dl><div><dt>{{ t("When") }}</dt><dd>{{ dateTimeText(item.scheduled_at) }}</dd></div></dl><details v-if="item.duration || item.interviewer || item.location"><summary>{{ t("Conversation details") }}</summary><dl><div v-if="item.duration"><dt>{{ t("Duration") }}</dt><dd>{{ item.duration }} {{ t("minutes") }}</dd></div><div v-if="item.interviewer"><dt>{{ t("Interviewer") }}</dt><dd>{{ item.interviewer }}</dd></div><div v-if="item.location"><dt>{{ t("Location") }}</dt><dd>{{ item.location }}</dd></div></dl></details>
          <Button v-if="item.meeting_url" as="a" :href="item.meeting_url" target="_blank" rel="noopener noreferrer" :label="t('Open meeting')" icon="pi pi-external-link" severity="secondary" outlined />
        </article>
      </div><Pagination v-model:page="upcomingPage" :total="upcoming.length" :page-size="pageSize" :label="t('upcoming interviews')" />
      </template><template #history><p v-if="!previous.length" class="empty-panel">{{ t("No history yet.") }}</p><template v-if="previous.length"><div class="cards"><article v-for="item in visiblePrevious" :key="item.id" class="work-card"><p class="due past">{{ interviewTypeText(item.type) }} {{ t("interview —") }} {{ relativeDateText(item.scheduled_at) }}</p><h3><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a></h3><p class="company">{{ item.application.company }} · {{ dateTimeText(item.scheduled_at) }}</p><p v-if="item.result">{{ item.result }}</p></article></div><Pagination v-model:page="previousPage" :total="previous.length" :page-size="pageSize" :label="t('previous interviews')" /></template>
      </template></PageTabs>
    </template>
  </section>
</template>

<style scoped>
@layer legacy {
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.group-title { margin: 28px 0 12px; } .group-title span { color: var(--at-text-muted); font-size: 13px; font-weight: 400; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.work-card { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; padding: 15px; }
.work-card.upcoming { border-top: 4px solid var(--at-interview); }
.work-card h3 { margin: 10px 0 4px; } .due { color: var(--at-interview); font-weight: 700; margin: 0; } .due.past, .company { color: var(--at-text-muted); }
dl { margin: 16px 0; } dl div { border-top: 1px solid var(--at-border); padding-top: 10px; margin-top: 10px; }
a { color: var(--at-link); text-underline-offset: 3px; } .empty-panel { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; padding: 32px; color: var(--at-text-muted); }
.previous-title { margin-top: 36px; }
}
summary { cursor:pointer; font-size:13px; color:var(--at-text-muted); margin-top:10px; }
</style>
