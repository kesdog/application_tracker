<script setup lang="ts">
import { version as appVersion } from '../package.json'
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import Drawer from 'primevue/drawer'
import WorkspaceNavigation from './WorkspaceNavigation.vue'
import { getApplication } from './api'
import ConfirmDialog from 'primevue/confirmdialog'
import Button from 'primevue/button'
import ToggleSwitch from 'primevue/toggleswitch'
import { appearanceSaveError, setThemeMode, themeMode } from './settings/appearanceStore'
import { navigationSaveError, sidebarCollapsed, toggleSidebar } from './settings/navigationPreferences'
import { browserSession, workspaceLogin } from './auth'
const props = withDefaults(defineProps<{ hosted?: boolean }>(), { hosted: false })
const emit = defineEmits<{ signout: []; openGuide: []; openLegal: [document: 'terms' | 'privacy'] }>()
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
  dashboard: 'Dashboard', applications: 'All applications', 'add-application': 'Add application',
  interviews: 'Interviews', tasks: 'Tasks', followups: 'Follow-ups', export: 'Export', settings: 'Settings',
})[page.value])
let events: EventSource | null = null

const mobileQuery = window.matchMedia('(max-width: 760px)')
const mobile = ref(mobileQuery.matches)
const mobileMenuOpen = ref(false)
const company = ref('')
let companyRequest = 0
const sectionIcon = computed(() => ({ dashboard: 'pi-home', applications: 'pi-briefcase', 'add-application': 'pi-plus-circle', interviews: 'pi-calendar', tasks: 'pi-check-square', followups: 'pi-envelope', export: 'pi-download', settings: 'pi-cog' })[page.value])
const sectionHref = computed(() => page.value === 'add-application' ? '#/applications/new' : page.value === 'export' ? '#/export' : `#/${page.value}`)
async function loadBreadcrumb() {
  const version = ++companyRequest
  company.value = ''
  const match = hash.value.match(/^#\/(?:applications|followups)\/([^/]+)/)
  if (!match || match[1] === 'new') return
  try {
    const record = await getApplication(match[1]!)
    if (version === companyRequest) company.value = record.company
  } catch { /* The page displays its own loading error. */ }
}
watch(hash, () => { mobileMenuOpen.value = false; void loadBreadcrumb() }, { immediate: true })
function screenChanged(event: MediaQueryListEvent) { mobile.value = event.matches; mobileMenuOpen.value = false }
function toggleNavigation() { if (mobile.value) mobileMenuOpen.value = !mobileMenuOpen.value; else toggleSidebar() }
function route() { hash.value = window.location.hash || '#/dashboard' }
function breadcrumbInvalidated() { if (company.value) void loadBreadcrumb() }

onMounted(() => {
  window.addEventListener('hashchange', route)
  window.addEventListener('tracker:invalidate', breadcrumbInvalidated)
  mobileQuery.addEventListener('change', screenChanged)
  events = new EventSource('/api/events')
  events.addEventListener('auth.expired', () => browserSession.expire())
  events.onerror = () => { if (props.hosted) void workspaceLogin.check() }
  for (const topic of ['application.updated', 'application.created', 'interview.updated', 'task.updated', 'followup.updated', 'recipient.updated']) {
    events.addEventListener(topic, (event) => window.dispatchEvent(new CustomEvent('tracker:invalidate', { detail: { topic, ...JSON.parse((event as MessageEvent).data) } })))
  }
})
onUnmounted(() => { companyRequest++; window.removeEventListener('hashchange', route); window.removeEventListener('tracker:invalidate', breadcrumbInvalidated); mobileQuery.removeEventListener('change', screenChanged); events?.close() })
</script>

<template>
  <div class="shell" :class="{ 'sidebar-collapsed': sidebarCollapsed && !mobile }">
    <ConfirmDialog />
    <a class="skip-link" href="#main-content" @click.prevent="mainContent?.focus()">Skip to content</a>
    <Drawer v-if="mobile" v-model:visible="mobileMenuOpen" position="left" header="My workspace" class="mobile-navigation" :pt="{ content: { style: 'padding: 0; display: flex; flex-direction: column;' } }">
      <WorkspaceNavigation :page="page" @navigate="mobileMenuOpen = false" />
    </Drawer>
    <WorkspaceNavigation v-else :page="page" />
    <div class="workspace">
      <header class="topbar"><Button type="button" class="sidebar-toggle" :icon="mobile || sidebarCollapsed ? 'pi pi-bars' : 'pi pi-angle-double-left'" severity="secondary" text :aria-label="mobile ? 'Open navigation' : sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :title="mobile ? 'Open navigation' : sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :aria-expanded="mobile ? mobileMenuOpen : !sidebarCollapsed" aria-controls="workspace-sidebar" @click="toggleNavigation" /><nav class="page-context breadcrumbs" aria-label="Breadcrumb"><a :href="sectionHref" :title="sectionTitle" :aria-label="sectionTitle" :aria-current="company ? undefined : 'page'"><i :class="`pi ${sectionIcon}`" aria-hidden="true" /><span>{{ sectionTitle }}</span></a><template v-if="company"><i class="pi pi-angle-right separator" aria-hidden="true" /><span class="current-company" :title="company" :aria-label="company" aria-current="page"><i class="pi pi-building" aria-hidden="true" /><span>{{ company }}</span></span></template></nav><div class="theme-control"><label for="workspace-theme"><i :class="darkTheme ? 'pi pi-moon' : 'pi pi-sun'" aria-hidden="true" /><span>{{ darkTheme ? 'Dark · Midnight' : 'Light · Paper' }}</span></label><ToggleSwitch input-id="workspace-theme" v-model="darkTheme" aria-label="Dark theme" /></div><Button v-if="hosted" type="button" severity="secondary" text @click="emit('signout')">Sign out</Button></header>
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
      <footer class="workspace-footer"><div>Application Tracker <span>{{ appVersion }}</span></div><nav aria-label="Help and legal"><Button type="button" text severity="secondary" @click="emit('openGuide')">Welcome guide</Button><Button type="button" text severity="secondary" @click="emit('openLegal', 'terms')">Terms and conditions</Button><Button type="button" text severity="secondary" @click="emit('openLegal', 'privacy')">Privacy &amp; cookies</Button></nav></footer>
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
.workspace-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }.workspace-footer nav { display:flex; gap:4px; flex-wrap:wrap; }
@media (max-width:760px) { .shell { flex-direction:column; }.sidebar { width:100%; height:auto; position:static; overflow:visible; flex-basis:auto; padding:12px 16px; border-right:0; border-bottom:1px solid var(--at-border); }.brand { padding:0 0 10px; }.primary-nav { flex-direction:row; flex-wrap:wrap; gap:2px; }.primary-nav a, .settings-nav a { padding:8px 10px; font-size:13px; }.nav-group { display:contents; }.subnav { display:contents; }.subnav a { font-size:12px; }.settings-nav { margin-top:4px; padding-top:4px; border-top:0; }.topbar { min-height:46px; padding:0 20px; } main { margin:24px auto; padding:0 20px; } footer { padding:16px 20px; } }
@media (max-width:480px) { main { padding:0 15px; }.primary-nav a, .settings-nav a { padding:7px 8px; } }
}
</style>
