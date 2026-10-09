<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import ConfirmDialog from 'primevue/confirmdialog'
import Button from 'primevue/button'
import ToggleSwitch from 'primevue/toggleswitch'
import { appearanceSaveError, setThemeMode, themeMode } from './settings/appearanceStore'
import { navigationSaveError, sidebarCollapsed, toggleSidebar } from './settings/navigationPreferences'
const Applications = defineAsyncComponent(() => import('./Applications.vue'))
const AddApplication = defineAsyncComponent(() => import('./AddApplication.vue'))
const Interviews = defineAsyncComponent(() => import('./Interviews.vue'))
const Tasks = defineAsyncComponent(() => import('./Tasks.vue'))
const Dashboard = defineAsyncComponent(() => import('./Dashboard.vue'))
const FollowUps = defineAsyncComponent(() => import('./FollowUps.vue'))
const AgentSettings = defineAsyncComponent(() => import('./AgentSettings.vue'))
const Exports = defineAsyncComponent(() => import('./Exports.vue'))

const hash = ref(window.location.hash || '#/dashboard')
const mainContent = ref<HTMLElement | null>(null)
const darkTheme = computed({ get: () => themeMode.value === 'dark', set: (dark: boolean) => setThemeMode(dark ? 'dark' : 'light') })
const page = computed(() => {
  if (hash.value === '#/applications/new') return 'add-application'
  if (hash.value.startsWith('#/export')) return 'export'
  if (hash.value.startsWith('#/settings')) return 'settings'
  if (hash.value.startsWith('#/interviews')) return 'interviews'
  if (hash.value.startsWith('#/tasks')) return 'tasks'
  if (hash.value.startsWith('#/followups')) return 'followups'
  if (hash.value.startsWith('#/applications')) return 'applications'
  return 'dashboard'
})
const sectionTitle = computed(() => ({
  dashboard: 'Dashboard', applications: 'Applications', 'add-application': 'Add application',
  interviews: 'Interviews', tasks: 'Tasks', followups: 'Follow-ups', export: 'Export', settings: 'Settings',
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
  <div class="shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <ConfirmDialog />
    <a class="skip-link" href="#main-content" @click.prevent="mainContent?.focus()">Skip to content</a>
    <aside id="workspace-sidebar" class="sidebar" aria-label="Workspace navigation">
      <a class="brand" href="#/dashboard" aria-label="Application Tracker — My workspace" title="Application Tracker"><span class="app-mark" aria-hidden="true">AT</span><span class="nav-label"><strong>Application Tracker</strong><small>My workspace</small></span></a>
      <nav class="primary-nav" aria-label="Primary">
        <a href="#/dashboard" aria-label="Dashboard" title="Dashboard" :class="{ active: page === 'dashboard' }" :aria-current="page === 'dashboard' ? 'page' : undefined"><i class="pi pi-home" aria-hidden="true" /><span class="nav-label">Dashboard</span></a>
        <div class="nav-group">
          <a href="#/applications" aria-label="Applications" title="Applications" :class="{ active: page === 'applications' || page === 'add-application' }" :aria-current="page === 'applications' ? 'page' : undefined"><i class="pi pi-briefcase" aria-hidden="true" /><span class="nav-label">Applications</span></a>
          <nav class="subnav" aria-label="Applications">
            <a href="#/applications" aria-label="All applications" title="All applications" :class="{ active: page === 'applications' }" :aria-current="page === 'applications' ? 'page' : undefined"><i class="pi pi-list" aria-hidden="true" /><span class="nav-label">All applications</span></a>
            <a href="#/applications/new" aria-label="Add application" title="Add application" :class="{ active: page === 'add-application' }" :aria-current="page === 'add-application' ? 'page' : undefined"><i class="pi pi-plus-circle" aria-hidden="true" /><span class="nav-label">Add application</span></a>
          </nav>
        </div>
        <a href="#/interviews" aria-label="Interviews" title="Interviews" :class="{ active: page === 'interviews' }" :aria-current="page === 'interviews' ? 'page' : undefined"><i class="pi pi-calendar" aria-hidden="true" /><span class="nav-label">Interviews</span></a>
        <a href="#/tasks" aria-label="Tasks" title="Tasks" :class="{ active: page === 'tasks' }" :aria-current="page === 'tasks' ? 'page' : undefined"><i class="pi pi-check-square" aria-hidden="true" /><span class="nav-label">Tasks</span></a>
        <a href="#/followups" aria-label="Follow-ups" title="Follow-ups" :class="{ active: page === 'followups' }" :aria-current="page === 'followups' ? 'page' : undefined"><i class="pi pi-envelope" aria-hidden="true" /><span class="nav-label">Follow-ups</span></a>
      </nav>
      <nav class="settings-nav" aria-label="Export and settings"><a href="#/export" aria-label="Export" title="Export" :class="{ active: page === 'export' }" :aria-current="page === 'export' ? 'page' : undefined"><i class="pi pi-download" aria-hidden="true" /><span class="nav-label">Export</span></a><a href="#/settings" aria-label="Settings" title="Settings" :class="{ active: page === 'settings' }" :aria-current="page === 'settings' ? 'page' : undefined"><i class="pi pi-cog" aria-hidden="true" /><span class="nav-label">Settings</span></a></nav>
    </aside>
    <div class="workspace">
      <header class="topbar"><Button type="button" class="sidebar-toggle" :icon="sidebarCollapsed ? 'pi pi-bars' : 'pi pi-angle-double-left'" severity="secondary" text :aria-label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :aria-expanded="!sidebarCollapsed" aria-controls="workspace-sidebar" @click="toggleSidebar" /><div class="page-context"><span>Workspace</span><strong>{{ sectionTitle }}</strong></div><div class="theme-control"><label for="workspace-theme"><i :class="darkTheme ? 'pi pi-moon' : 'pi pi-sun'" aria-hidden="true" /><span>{{ darkTheme ? 'Dark · Midnight' : 'Light · Paper' }}</span></label><ToggleSwitch input-id="workspace-theme" v-model="darkTheme" aria-label="Dark theme" /></div></header>
      <p v-if="appearanceSaveError || navigationSaveError" class="preference-notice at-message warning" role="status">{{ appearanceSaveError || navigationSaveError }}</p>
      <main ref="mainContent" id="main-content" tabindex="-1">
        <Dashboard v-if="page === 'dashboard'" />
        <AddApplication v-else-if="page === 'add-application'" />
        <Interviews v-else-if="page === 'interviews'" />
        <Tasks v-else-if="page === 'tasks'" />
        <FollowUps v-else-if="page === 'followups'" />
        <Exports v-else-if="page === 'export'" />
        <AgentSettings v-else-if="page === 'settings'" />
        <Applications v-else />
      </main>
      <footer>Application Tracker <span>0.11.0</span></footer>
    </div>
  </div>
</template>

<style>
@layer legacy {
:root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--at-text); background: var(--at-background); font-synthesis: none; }
* { box-sizing: border-box; }
body { margin: 0; }
.shell { min-height: 100vh; display: flex; }
.skip-link { position:fixed; top:-100px; left:16px; z-index:100; padding:12px; background:var(--at-surface); }.skip-link:focus { top:12px; }
.sidebar { width: 238px; flex: 0 0 238px; height: 100vh; position: sticky; top: 0; overflow-y: auto; display: flex; flex-direction: column; padding: 22px 14px; background: var(--at-surface); border-right: 1px solid var(--at-border); }
.brand { display:flex; align-items:center; gap:11px; padding: 4px 7px 28px; color:var(--at-text); text-decoration:none; }
.brand strong { display:block; font-size:15px; line-height:1.2; }.brand small { display:block; color:var(--at-text-muted); font-size:11px; margin-top:4px; }
.app-mark { display:grid; place-items:center; width:36px; height:36px; flex:0 0 36px; background:var(--at-primary); color:var(--at-primary-contrast); font-size:13px; font-weight:700; border-radius:8px; }
.primary-nav, .settings-nav, .subnav { display:flex; flex-direction:column; gap:3px; }
.primary-nav a > i, .settings-nav a > i { width:18px; margin-right:8px; font-size:14px; text-align:center; }
.settings-nav { margin-top:auto; padding-top:18px; border-top:1px solid var(--at-border); }
.primary-nav a, .settings-nav a { display:block; border-radius:7px; padding:11px 13px; color:var(--at-text-muted); text-decoration:none; font-size:14px; font-weight:600; }
.primary-nav a:hover, .settings-nav a:hover, .primary-nav a.active, .settings-nav a.active { background:var(--at-surface-muted); color:var(--at-primary); }
.subnav { margin:2px 0 7px 12px; padding-left:9px; border-left:1px solid var(--at-border); }
.subnav a { padding:8px 12px; font-size:13px; font-weight:500; }
.subnav a.active { font-weight:700; }
.workspace { min-width:0; flex:1; display:flex; flex-direction:column; }
.topbar { display:flex; align-items:center; gap:8px; min-height:64px; padding:0 32px; background:var(--at-surface); border-bottom:1px solid var(--at-border); color:var(--at-text-muted); font-size:13px; }
.topbar strong { color:var(--at-text); font-weight:650; }.topbar strong::before { content:'/'; color:var(--at-text-muted); margin-right:8px; }
main { width:min(100%, 1280px); margin:32px auto; padding:0 32px; flex:1; }
.eyebrow { color:var(--at-text-muted); font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; margin:0 0 12px; }
h2 { font-size:28px; letter-spacing:-.02em; margin:0 0 10px; }
h3 { font-size:17px; margin:0; }
.intro { color:var(--at-text-muted); margin:0 0 28px; line-height:1.5; }
button { font:inherit; font-size:13px; font-weight:600; color:var(--at-primary); background:var(--at-surface); border:1px solid var(--at-border); border-radius:6px; padding:9px 13px; cursor:pointer; }
button:hover:enabled { background:var(--at-surface-muted); } button:disabled { opacity:.6; cursor:wait; } button:focus-visible, a:focus-visible { outline:3px solid var(--at-focus); outline-offset:3px; }
.message, .error { font-size:14px; line-height:1.6; margin:16px 0 24px; }.message { color:var(--at-text-muted); }.error { color:var(--at-unsuccessful); }
dl { margin:0; border-top:1px solid var(--at-border); padding-top:8px; }
dl div { display:flex; justify-content:space-between; gap:16px; padding-top:16px; font-size:14px; }
dt { color:var(--at-text-muted); } dd { margin:0; font-weight:550; text-align:right; }
footer { padding:20px 32px; color:var(--at-text-muted); font-size:12px; } footer span { margin-left:8px; }
@media (max-width:760px) { .shell { flex-direction:column; }.sidebar { width:100%; height:auto; position:static; overflow:visible; flex-basis:auto; padding:12px 16px; border-right:0; border-bottom:1px solid var(--at-border); }.brand { padding:0 0 10px; }.primary-nav { flex-direction:row; flex-wrap:wrap; gap:2px; }.primary-nav a, .settings-nav a { padding:8px 10px; font-size:13px; }.nav-group { display:contents; }.subnav { display:contents; }.subnav a { font-size:12px; }.settings-nav { margin-top:4px; padding-top:4px; border-top:0; }.topbar { min-height:46px; padding:0 20px; } main { margin:24px auto; padding:0 20px; } footer { padding:16px 20px; } }
@media (max-width:480px) { main { padding:0 15px; }.primary-nav a, .settings-nav a { padding:7px 8px; } }
}
</style>
