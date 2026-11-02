<script setup lang="ts">
import { t, messageText } from './i18n'

defineProps<{ page: string }>()
const emit = defineEmits<{ navigate: [] }>()
function closeOnNavigation(event: MouseEvent) {
  if ((event.target as Element).closest('a[href]')) emit('navigate')
}
</script>
<template>
    <aside id="workspace-sidebar" @click="closeOnNavigation" class="sidebar" :aria-label="t('Workspace navigation')">
      <a class="brand" href="#/dashboard" :aria-label="t('Application Tracker — My workspace')" :title="t('Application Tracker')"><span class="app-mark" aria-hidden="true">{{ t("AT") }}</span><span class="nav-label"><strong>{{ t("Application Tracker") }}</strong><small>{{ t("My workspace") }}</small></span></a>
      <nav class="primary-nav" :aria-label="t('Primary')">
        <a href="#/dashboard" :aria-label="t('Dashboard')" :title="t('Dashboard')" :class="{ active: page === 'dashboard' }" :aria-current="page === 'dashboard' ? 'page' : undefined"><i class="pi pi-home" aria-hidden="true" /><span class="nav-label">{{ t("Dashboard") }}</span></a>
        <a href="#/applications" :aria-label="t('All applications')" :title="t('All applications')" :class="{ active: page === 'applications' }" :aria-current="page === 'applications' ? 'page' : undefined"><i class="pi pi-briefcase" aria-hidden="true" /><span class="nav-label">{{ t("All applications") }}</span></a>
        <a href="#/applications/new" :aria-label="t('Add application')" :title="t('Add application')" :class="{ active: page === 'add-application' }" :aria-current="page === 'add-application' ? 'page' : undefined"><i class="pi pi-plus-circle" aria-hidden="true" /><span class="nav-label">{{ t("Add application") }}</span></a>
        <a href="#/interviews" :aria-label="t('Interviews')" :title="t('Interviews')" :class="{ active: page === 'interviews' }" :aria-current="page === 'interviews' ? 'page' : undefined"><i class="pi pi-calendar" aria-hidden="true" /><span class="nav-label">{{ t("Interviews") }}</span></a>
        <a href="#/tasks" :aria-label="t('Tasks')" :title="t('Tasks')" :class="{ active: page === 'tasks' }" :aria-current="page === 'tasks' ? 'page' : undefined"><i class="pi pi-check-square" aria-hidden="true" /><span class="nav-label">{{ t("Tasks") }}</span></a>
        <a href="#/followups" :aria-label="t('Follow-ups')" :title="t('Follow-ups')" :class="{ active: page === 'followups' }" :aria-current="page === 'followups' ? 'page' : undefined"><i class="pi pi-envelope" aria-hidden="true" /><span class="nav-label">{{ t("Follow-ups") }}</span></a>
      </nav>
      <nav class="settings-nav" :aria-label="t('Export and settings')"><a href="#/export" :aria-label="t('Export')" :title="t('Export')" :class="{ active: page === 'export' }" :aria-current="page === 'export' ? 'page' : undefined"><i class="pi pi-download" aria-hidden="true" /><span class="nav-label">{{ t("Export") }}</span></a><a href="#/settings" :aria-label="t('Settings')" :title="t('Settings')" :class="{ active: page === 'settings' }" :aria-current="page === 'settings' ? 'page' : undefined"><i class="pi pi-cog" aria-hidden="true" /><span class="nav-label">{{ t("Settings") }}</span></a></nav>
    </aside>
</template>
