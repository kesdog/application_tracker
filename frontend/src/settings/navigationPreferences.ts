import { ref } from 'vue'
import { readPreference, writePreference } from './localPreferences'

export const sidebarStorageKey = 'application-tracker:sidebar-collapsed'
export const sidebarCollapsed = ref(readPreference(sidebarStorageKey) === true)
export const navigationSaveError = ref('')
export function toggleSidebar(): void {
  sidebarCollapsed.value = !sidebarCollapsed.value
  navigationSaveError.value = writePreference(sidebarStorageKey, sidebarCollapsed.value) ? '' : 'Sidebar changed for this session. Your browser could not save it for the next visit.'
}
