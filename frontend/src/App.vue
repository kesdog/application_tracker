<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import Applications from './Applications.vue'
import AddApplication from './AddApplication.vue'
import Interviews from './Interviews.vue'
import Tasks from './Tasks.vue'
import Dashboard from './Dashboard.vue'
import AgentSettings from './AgentSettings.vue'

const hash = ref(window.location.hash || '#/dashboard')
const page = computed(() => {
  if (hash.value === '#/applications/new') return 'add-application'
  if (hash.value.startsWith('#/settings')) return 'settings'
  if (hash.value.startsWith('#/interviews')) return 'interviews'
  if (hash.value.startsWith('#/tasks')) return 'tasks'
  if (hash.value.startsWith('#/applications')) return 'applications'
  return 'dashboard'
})
const sectionTitle = computed(() => ({
  dashboard: 'Dashboard', applications: 'Applications', 'add-application': 'Add application',
  interviews: 'Interviews', tasks: 'Tasks', settings: 'Settings',
})[page.value])
let events: EventSource | null = null

function route() { hash.value = window.location.hash || '#/dashboard' }

onMounted(() => {
  window.addEventListener('hashchange', route)
  events = new EventSource('/api/events')
  for (const topic of ['application.updated', 'application.created', 'interview.updated', 'task.updated', 'followup.updated']) {
    events.addEventListener(topic, (event) => window.dispatchEvent(new CustomEvent('tracker:invalidate', { detail: { topic, ...JSON.parse((event as MessageEvent).data) } })))
  }
})
onUnmounted(() => { window.removeEventListener('hashchange', route); events?.close() })
</script>

<template>
  <div class="shell">
    <aside class="sidebar" aria-label="Workspace navigation">
      <a class="brand" href="#/dashboard"><span class="app-mark" aria-hidden="true">AT</span><span><strong>Application Tracker</strong><small>My workspace</small></span></a>
      <nav class="primary-nav" aria-label="Primary">
        <a href="#/dashboard" :class="{ active: page === 'dashboard' }" :aria-current="page === 'dashboard' ? 'page' : undefined">Dashboard</a>
        <div class="nav-group">
          <a href="#/applications" :class="{ active: page === 'applications' || page === 'add-application' }" :aria-current="page === 'applications' ? 'page' : undefined">Applications</a>
          <nav class="subnav" aria-label="Applications">
            <a href="#/applications" :class="{ active: page === 'applications' }" :aria-current="page === 'applications' ? 'page' : undefined">All applications</a>
            <a href="#/applications/new" :class="{ active: page === 'add-application' }" :aria-current="page === 'add-application' ? 'page' : undefined">Add application</a>
          </nav>
        </div>
        <a href="#/interviews" :class="{ active: page === 'interviews' }" :aria-current="page === 'interviews' ? 'page' : undefined">Interviews</a>
        <a href="#/tasks" :class="{ active: page === 'tasks' }" :aria-current="page === 'tasks' ? 'page' : undefined">Tasks</a>
      </nav>
      <nav class="settings-nav" aria-label="Settings"><a href="#/settings" :class="{ active: page === 'settings' }" :aria-current="page === 'settings' ? 'page' : undefined">Settings</a></nav>
    </aside>
    <div class="workspace">
      <header class="topbar"><span>Workspace</span><strong>{{ sectionTitle }}</strong></header>
      <main id="main-content">
        <Dashboard v-if="page === 'dashboard'" />
        <AddApplication v-else-if="page === 'add-application'" />
        <Interviews v-else-if="page === 'interviews'" />
        <Tasks v-else-if="page === 'tasks'" />
        <AgentSettings v-else-if="page === 'settings'" />
        <Applications v-else />
      </main>
      <footer>Application Tracker <span>0.10.0</span></footer>
    </div>
  </div>
</template>

<style>
:root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202c3d; background: #f5f6f8; font-synthesis: none; }
* { box-sizing: border-box; }
body { margin: 0; }
.shell { min-height: 100vh; display: flex; }
.sidebar { width: 238px; flex: 0 0 238px; height: 100vh; position: sticky; top: 0; overflow-y: auto; display: flex; flex-direction: column; padding: 22px 14px; background: #fff; border-right: 1px solid #dde2e9; }
.brand { display:flex; align-items:center; gap:11px; padding: 4px 7px 28px; color:#202c3d; text-decoration:none; }
.brand strong { display:block; font-size:15px; line-height:1.2; }.brand small { display:block; color:#718095; font-size:11px; margin-top:4px; }
.app-mark { display:grid; place-items:center; width:36px; height:36px; flex:0 0 36px; background:#263e5c; color:#fff; font-size:13px; font-weight:700; border-radius:8px; }
.primary-nav, .settings-nav, .subnav { display:flex; flex-direction:column; gap:3px; }
.settings-nav { margin-top:auto; padding-top:18px; border-top:1px solid #e5e9ee; }
.primary-nav a, .settings-nav a { display:block; border-radius:7px; padding:11px 13px; color:#526174; text-decoration:none; font-size:14px; font-weight:600; }
.primary-nav a:hover, .settings-nav a:hover, .primary-nav a.active, .settings-nav a.active { background:#edf1f5; color:#1f3857; }
.subnav { margin:2px 0 7px 12px; padding-left:9px; border-left:1px solid #d7e0e9; }
.subnav a { padding:8px 12px; font-size:13px; font-weight:500; }
.subnav a.active { font-weight:700; }
.workspace { min-width:0; flex:1; display:flex; flex-direction:column; }
.topbar { display:flex; align-items:center; gap:8px; min-height:64px; padding:0 32px; background:#fff; border-bottom:1px solid #dde2e9; color:#718095; font-size:13px; }
.topbar strong { color:#202c3d; font-weight:650; }.topbar strong::before { content:'/'; color:#a8b3c1; margin-right:8px; }
main { width:min(100%, 1280px); margin:32px auto; padding:0 32px; flex:1; }
.eyebrow { color:#576678; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; margin:0 0 12px; }
h2 { font-size:28px; letter-spacing:-.02em; margin:0 0 10px; }
h3 { font-size:17px; margin:0; }
.intro { color:#576678; margin:0 0 28px; line-height:1.5; }
button { font:inherit; font-size:13px; font-weight:600; color:#293e58; background:#fff; border:1px solid #b9c4d2; border-radius:6px; padding:9px 13px; cursor:pointer; }
button:hover:enabled { background:#f0f3f7; } button:disabled { opacity:.6; cursor:wait; } button:focus-visible, a:focus-visible { outline:3px solid #527ba8; outline-offset:3px; }
.message, .error { font-size:14px; line-height:1.6; margin:16px 0 24px; }.message { color:#576678; }.error { color:#a12c32; }
dl { margin:0; border-top:1px solid #e5e9ee; padding-top:8px; }
dl div { display:flex; justify-content:space-between; gap:16px; padding-top:16px; font-size:14px; }
dt { color:#576678; } dd { margin:0; font-weight:550; text-align:right; }
footer { padding:20px 32px; color:#627084; font-size:12px; } footer span { margin-left:8px; }
@media (max-width:760px) { .shell { flex-direction:column; }.sidebar { width:100%; height:auto; position:static; overflow:visible; flex-basis:auto; padding:12px 16px; border-right:0; border-bottom:1px solid #dde2e9; }.brand { padding:0 0 10px; }.primary-nav { flex-direction:row; flex-wrap:wrap; gap:2px; }.primary-nav a, .settings-nav a { padding:8px 10px; font-size:13px; }.nav-group { display:contents; }.subnav { display:contents; }.subnav a { font-size:12px; }.settings-nav { margin-top:4px; padding-top:4px; border-top:0; }.topbar { min-height:46px; padding:0 20px; } main { margin:24px auto; padding:0 20px; } footer { padding:16px 20px; } }
@media (max-width:480px) { main { padding:0 15px; }.primary-nav a, .settings-nav a { padding:7px 8px; } }
</style>
