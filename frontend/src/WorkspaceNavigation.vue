<script setup lang="ts">
defineProps<{ page: string }>()
const emit = defineEmits<{ navigate: [] }>()
function closeOnNavigation(event: MouseEvent) {
  if ((event.target as Element).closest('a[href]')) emit('navigate')
}
</script>
<template>
    <aside id="workspace-sidebar" @click="closeOnNavigation" class="sidebar" aria-label="Workspace navigation">
      <a class="brand" href="#/dashboard" aria-label="Application Tracker — My workspace" title="Application Tracker"><span class="app-mark" aria-hidden="true">AT</span><span class="nav-label"><strong>Application Tracker</strong><small>My workspace</small></span></a>
      <nav class="primary-nav" aria-label="Primary">
        <a href="#/dashboard" aria-label="Dashboard" title="Dashboard" :class="{ active: page === 'dashboard' }" :aria-current="page === 'dashboard' ? 'page' : undefined"><i class="pi pi-home" aria-hidden="true" /><span class="nav-label">Dashboard</span></a>
        <a href="#/applications" aria-label="All applications" title="All applications" :class="{ active: page === 'applications' }" :aria-current="page === 'applications' ? 'page' : undefined"><i class="pi pi-briefcase" aria-hidden="true" /><span class="nav-label">All applications</span></a>
        <a href="#/applications/new" aria-label="Add application" title="Add application" :class="{ active: page === 'add-application' }" :aria-current="page === 'add-application' ? 'page' : undefined"><i class="pi pi-plus-circle" aria-hidden="true" /><span class="nav-label">Add application</span></a>
        <a href="#/interviews" aria-label="Interviews" title="Interviews" :class="{ active: page === 'interviews' }" :aria-current="page === 'interviews' ? 'page' : undefined"><i class="pi pi-calendar" aria-hidden="true" /><span class="nav-label">Interviews</span></a>
        <a href="#/tasks" aria-label="Tasks" title="Tasks" :class="{ active: page === 'tasks' }" :aria-current="page === 'tasks' ? 'page' : undefined"><i class="pi pi-check-square" aria-hidden="true" /><span class="nav-label">Tasks</span></a>
        <a href="#/followups" aria-label="Follow-ups" title="Follow-ups" :class="{ active: page === 'followups' }" :aria-current="page === 'followups' ? 'page' : undefined"><i class="pi pi-envelope" aria-hidden="true" /><span class="nav-label">Follow-ups</span></a>
      </nav>
      <nav class="settings-nav" aria-label="Export and settings"><a href="#/export" aria-label="Export" title="Export" :class="{ active: page === 'export' }" :aria-current="page === 'export' ? 'page' : undefined"><i class="pi pi-download" aria-hidden="true" /><span class="nav-label">Export</span></a><a href="#/settings" aria-label="Settings" title="Settings" :class="{ active: page === 'settings' }" :aria-current="page === 'settings' ? 'page' : undefined"><i class="pi pi-cog" aria-hidden="true" /><span class="nav-label">Settings</span></a></nav>
    </aside>
</template>
