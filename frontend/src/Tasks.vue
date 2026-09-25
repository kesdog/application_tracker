<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { listTasks, updateTask, type TaskListItem } from './api'
import { dateTimeText, relativeDateText } from './dateText'

const tasks = ref<TaskListItem[]>([])
const loading = ref(false)
const error = ref('')
const pending = computed(() => tasks.value.filter(item => item.status === 'PENDING'))
const finished = computed(() => tasks.value.filter(item => item.status !== 'PENDING'))

async function load() {
  loading.value = true; error.value = ''
  try { tasks.value = await listTasks() }
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
    <div class="page-heading"><div><p class="eyebrow">Upcoming work</p><h2 id="tasks-page-title">Tasks</h2></div><button type="button" :disabled="loading" @click="load">{{ loading ? 'Working…' : 'Refresh' }}</button></div>
    <p class="intro">See every application task in due-date order.</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading && !tasks.length" role="status">Loading tasks…</p>
    <div v-else-if="!tasks.length" class="empty-panel">No tasks yet. Add one from an application.</div>
    <template v-else>
      <h3 class="group-title">To do <span>{{ pending.length }}</span></h3>
      <div class="task-list"><article v-for="item in pending" :key="item.id" class="task-row">
        <div><p class="due">{{ item.title }} — {{ item.due_at ? relativeDateText(item.due_at, 'due ') : 'no due date' }}</p><p class="context"><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }}</p><p v-if="item.description" class="description">{{ item.description }}</p><p v-if="item.due_at" class="exact">{{ dateTimeText(item.due_at) }}</p></div>
        <div class="actions"><button type="button" :disabled="loading" @click="setStatus(item, 'COMPLETED')">Complete</button><button type="button" :disabled="loading" @click="setStatus(item, 'CANCELLED')">Cancel</button></div>
      </article></div>
      <template v-if="finished.length"><h3 class="group-title finished-title">Completed or cancelled <span>{{ finished.length }}</span></h3><div class="task-list"><article v-for="item in finished" :key="item.id" class="task-row muted-row"><div><p class="due">{{ item.title }}</p><p class="context"><a :href="`#/applications/${item.application.id}`">{{ item.application.job_title }}</a> · {{ item.application.company }} · {{ item.status }}</p></div><button type="button" :disabled="loading" @click="setStatus(item, 'PENDING')">Reopen</button></article></div></template>
    </template>
  </section>
</template>

<style scoped>
.page-heading, .task-row, .actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.group-title { margin: 28px 0 12px; } .group-title span { color: #627084; font-size: 13px; font-weight: 400; }
.task-list { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; overflow: hidden; }
.task-row { padding: 18px 20px; border-bottom: 1px solid #e5e9ee; align-items: flex-start; } .task-row:last-child { border-bottom: 0; }
.due { font-weight: 700; margin: 0 0 6px; } .context, .description, .exact { color: #576678; font-size: 13px; margin: 5px 0; }
.muted-row { background: #fafbfc; } .finished-title { margin-top: 36px; } a { color: #24568b; text-underline-offset: 3px; }
.empty-panel { background: #fff; border: 1px solid #dce2e9; border-radius: 8px; padding: 32px; color: #576678; }
@media (max-width: 600px) { .task-row { flex-direction: column; } }
</style>
