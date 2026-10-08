<script setup lang="ts">
import Button from 'primevue/button'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { listTasks, updateTask, type TaskListItem } from './api'
import { dateTimeText, relativeDateText } from './dateText'
import Pagination from './Pagination.vue'
import AppTag from './components/shared/AppTag.vue'
import { taskStatusMeta, urgencyMeta } from './presentation/taskPresentation'

const tasks = ref<TaskListItem[]>([])
const loading = ref(false)
const error = ref('')
const pendingPage = ref(1)
const finishedPage = ref(1)
const pageSize = 10
const pending = computed(() => tasks.value.filter(item => item.status === 'PENDING'))
const finished = computed(() => tasks.value.filter(item => item.status !== 'PENDING'))
const visiblePending = computed(() => pending.value.slice((pendingPage.value - 1) * pageSize, pendingPage.value * pageSize))
const visibleFinished = computed(() => finished.value.slice((finishedPage.value - 1) * pageSize, finishedPage.value * pageSize))

async function load() {
  loading.value = true; error.value = ''
  try { tasks.value = await listTasks(); pendingPage.value = 1; finishedPage.value = 1 }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load tasks.' }
  finally { loading.value = false }
}

async function setStatus(item: TaskListItem, status: TaskListItem['status']) {
  loading.value = true; error.value = ''
  try {
    const saved = await updateTask(item.application_id, item.id, { status })
    tasks.value = tasks.value.map(row => row.id === saved.id ? { ...row, ...saved } : row)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to update task.' }
  finally { loading.value = false }
}

const onInvalidation = () => { void load() }
onMounted(() => { void load(); window.addEventListener('tracker:invalidate', onInvalidation) })
onUnmounted(() => window.removeEventListener('tracker:invalidate', onInvalidation))
</script>

<template>
  <section aria-labelledby="tasks-page-title">
    <div class="page-heading"><div><p class="eyebrow">Upcoming work</p><h2 id="tasks-page-title">Tasks</h2></div><Button type="button" :disabled="loading" @click="load">{{ loading ? 'Working…' : 'Refresh' }}</Button></div>
    <p class="intro">See every application task in due-date order.</p>
    <p v-if="error" class="at-message error" role="alert">{{ error }}</p>
    <p v-if="loading && !tasks.length" role="status">Loading tasks…</p>
    <div v-else-if="!tasks.length" class="empty-panel">No tasks yet. Add one from an application.</div>
    <template v-else>
      <h3 class="group-title">To do <span>{{ pending.length }}</span></h3>
      <div class="task-list"><article v-for="item in visiblePending" :key="item.id" class="task-row" :class="{ overdue: urgencyMeta(item.due_at).tone === 'overdue' }">
        <div><p class="due">{{ item.title }} — {{ item.due_at ? relativeDateText(item.due_at, 'due ') : 'no due date' }}</p><AppTag v-bind="urgencyMeta(item.due_at)" /><p class="context"><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }}</p><p v-if="item.description" class="description">{{ item.description }}</p><p v-if="item.due_at" class="exact">{{ dateTimeText(item.due_at) }}</p></div>
        <div class="actions"><Button type="button" :disabled="loading" @click="setStatus(item, 'COMPLETED')">Complete</Button><Button type="button" :disabled="loading" @click="setStatus(item, 'CANCELLED')">Cancel</Button></div>
      </article><Pagination v-model:page="pendingPage" :total="pending.length" :page-size="pageSize" label="tasks" /></div>
      <template v-if="finished.length"><h3 class="group-title finished-title">Completed or cancelled <span>{{ finished.length }}</span></h3><div class="task-list"><article v-for="item in visibleFinished" :key="item.id" class="task-row muted-row"><div><p class="due">{{ item.title }}</p><AppTag v-bind="taskStatusMeta[item.status]" /><p class="context"><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }}</p></div><Button type="button" :disabled="loading" @click="setStatus(item, 'PENDING')">Reopen</Button></article><Pagination v-model:page="finishedPage" :total="finished.length" :page-size="pageSize" label="completed tasks" /></div></template>
    </template>
  </section>
</template>

<style scoped>
@layer legacy {
.page-heading, .task-row, .actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.group-title { margin: 28px 0 12px; } .group-title span { color: var(--at-text-muted); font-size: 13px; font-weight: 400; }
.task-list { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; overflow: hidden; }
.task-row { padding: 12px 14px; border-bottom: 1px solid var(--at-border); align-items: flex-start; } .task-row:last-child { border-bottom: 0; }
.task-row.overdue { box-shadow:inset 3px 0 var(--at-overdue); background:color-mix(in srgb, var(--at-overdue) 6%, var(--at-surface)); }.actions { flex-wrap:wrap; }
.due { font-weight: 700; margin: 0 0 6px; } .context, .description, .exact { color: var(--at-text-muted); font-size: 13px; margin: 5px 0; }
.muted-row { background: var(--at-surface-muted); } .finished-title { margin-top: 36px; } a { color: var(--at-link); text-underline-offset: 3px; }
.empty-panel { background: var(--at-surface); border: 1px solid var(--at-border); border-radius: 8px; padding: 32px; color: var(--at-text-muted); }
@media (max-width: 600px) { .task-row { flex-direction: column; } }
}
</style>
