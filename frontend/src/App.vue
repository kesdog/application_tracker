<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getHealth, type Health } from './api'
import Applications from './Applications.vue'
import Interviews from './Interviews.vue'
import Tasks from './Tasks.vue'
import Dashboard from './Dashboard.vue'
import AgentSettings from './AgentSettings.vue'

const status = ref<'checking' | 'connected' | 'disconnected'>('checking')
const health = ref<Health | null>(null)
const hash = ref(window.location.hash || '#/applications')
const page = computed(() => hash.value.startsWith('#/settings') ? 'settings' : hash.value.startsWith('#/dashboard') ? 'dashboard' : hash.value.startsWith('#/interviews') ? 'interviews' : hash.value.startsWith('#/tasks') ? 'tasks' : 'applications')
let events: EventSource | null = null
function route() { hash.value = window.location.hash || '#/applications' }

async function checkConnection() {
  status.value = 'checking'
  health.value = null
  try {
    health.value = await getHealth()
    status.value = 'connected'
  } catch {
    status.value = 'disconnected'
  }
}

onMounted(() => {
  window.addEventListener('hashchange', route); void checkConnection()
  events = new EventSource('/api/events')
  for (const topic of ['application.updated', 'application.created', 'interview.updated', 'task.updated', 'followup.updated']) {
    events.addEventListener(topic, (event) => window.dispatchEvent(new CustomEvent('tracker:invalidate', { detail: { topic, ...JSON.parse((event as MessageEvent).data) } })))
  }
})
onUnmounted(() => { window.removeEventListener('hashchange', route); events?.close() })
</script>

<template>
  <div class="shell">
    <header><div class="brand"><span class="app-mark" aria-hidden="true">AT</span><h1>Application Tracker</h1></div><nav aria-label="Primary"><a href="#/dashboard" :class="{ active: page === 'dashboard' }">Dashboard</a><a href="#/applications" :class="{ active: page === 'applications' }">Applications</a><a href="#/interviews" :class="{ active: page === 'interviews' }">Interviews</a><a href="#/tasks" :class="{ active: page === 'tasks' }">Tasks</a><a href="#/settings" :class="{ active: page === 'settings' }">Settings</a></nav></header>
    <main>
      <Dashboard v-if="page === 'dashboard'" />
      <Interviews v-else-if="page === 'interviews'" />
      <Tasks v-else-if="page === 'tasks'" />
      <AgentSettings v-else-if="page === 'settings'" />
      <Applications v-else />

      <details class="system-status"><summary>System status · {{ status === 'connected' ? `Connected · ${health?.version}` : status }}</summary>
      <section class="status-card" aria-label="Connection status" aria-live="polite" :aria-busy="status === 'checking'">
        <div class="status-heading">
          <h3 :class="status"><span class="dot" aria-hidden="true"></span>Backend: {{ status === 'checking' ? 'Checking…' : status === 'connected' ? 'Connected' : 'Disconnected' }}</h3>
          <button type="button" :disabled="status === 'checking'" @click="checkConnection">{{ status === 'checking' ? 'Checking…' : 'Check again' }}</button>
        </div>
        <p v-if="status === 'disconnected'" class="error">Unable to reach the backend. Make sure it is running, then check again or refresh this page.</p>
        <p v-else-if="status === 'connected'" class="message">The backend is reachable and your local database is ready.</p>
        <p v-else class="message">Connecting to your local backend…</p>
        <dl>
          <div><dt>Backend version</dt><dd>{{ health?.version ?? 'Unavailable' }}</dd></div>
          <div><dt>Database</dt><dd>{{ health ? 'SQLite · Connected' : 'Unavailable' }}</dd></div>
        </dl>
      </section>
      </details>
    </main>
    <footer>Application Tracker <span>0.10.0</span></footer>
  </div>
</template>

<style>
:root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202c3d; background: #f5f6f8; font-synthesis: none; }
* { box-sizing: border-box; }
body { margin: 0; }
.shell { min-height: 100vh; display: flex; flex-direction: column; }
header { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 16px 32px; background: #fff; border-bottom: 1px solid #dde2e9; }
.brand, nav { display: flex; align-items: center; gap: 12px; }
nav { gap: 6px; } nav a { color: #526174; text-decoration: none; font-size: 14px; font-weight: 600; padding: 9px 11px; border-radius: 6px; } nav a:hover, nav a.active { background: #edf1f5; color: #1f3857; }
.app-mark { padding: 8px; background: #263e5c; color: #fff; font-size: 13px; font-weight: 700; border-radius: 6px; }
h1 { font-size: 17px; font-weight: 650; margin: 0; }
main { width: min(100%, 1200px); margin: 40px auto; padding: 0 24px; flex: 1; }
.system-status { margin-top: 32px; } summary { cursor: pointer; color: #576678; font-size: 13px; padding: 12px 0; }
.eyebrow { color: #576678; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; margin: 0 0 12px; }
h2 { font-size: 28px; letter-spacing: -.02em; margin: 0 0 10px; }
.intro { color: #576678; margin: 0 0 28px; line-height: 1.5; }
.status-card { background: #fff; border: 1px solid #dce2e9; border-radius: 10px; padding: 24px; }
.status-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
h3 { display: flex; align-items: center; gap: 9px; font-size: 17px; margin: 0; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: currentColor; }
.connected { color: #216344; } .disconnected, .error { color: #a12c32; } .checking { color: #576678; }
button { font: inherit; font-size: 13px; font-weight: 600; color: #293e58; background: #fff; border: 1px solid #b9c4d2; border-radius: 6px; padding: 9px 13px; cursor: pointer; }
button:hover:enabled { background: #f0f3f7; } button:disabled { opacity: .6; cursor: wait; } button:focus-visible { outline: 3px solid #527ba8; outline-offset: 3px; }
.message, .error { font-size: 14px; line-height: 1.6; margin: 16px 0 24px; } .message { color: #576678; }
dl { margin: 0; border-top: 1px solid #e5e9ee; padding-top: 8px; }
dl div { display: flex; justify-content: space-between; gap: 16px; padding-top: 16px; font-size: 14px; }
dt { color: #576678; } dd { margin: 0; font-weight: 550; text-align: right; }
footer { padding: 20px 32px; color: #627084; font-size: 12px; } footer span { margin-left: 8px; }
@media (max-width: 600px) { header { padding: 14px 16px; align-items: flex-start; flex-direction: column; } nav { width: 100%; justify-content: space-between; gap: 2px; flex-wrap:wrap; } nav a { padding: 8px 6px; font-size: 12px; } main { margin: 30px auto; padding: 0 16px; } .status-card { padding: 20px; } h2 { font-size: 25px; } }
</style>
