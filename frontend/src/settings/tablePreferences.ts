import { reactive, readonly, ref } from 'vue'
import { readPreference, writePreference } from './localPreferences'

export const optionalColumns = [
  { value: 'location', label: 'Location' }, { value: 'contract', label: 'Contract' },
  { value: 'outcome', label: 'Outcome' }, { value: 'nextAction', label: 'Next action' },
  { value: 'source', label: 'Source' },
] as const
export type OptionalColumn = typeof optionalColumns[number]['value']
export interface TablePreferences { version: 1; columns: OptionalColumn[]; density: 'compact' | 'comfortable'; pageSize: number }
export const tablePreferencesKey = 'application-tracker:table-preferences'
export const defaultTablePreferences = (): TablePreferences => ({ version: 1, columns: optionalColumns.map(c => c.value), density: 'compact', pageSize: 20 })
export function parseTablePreferences(value: unknown): TablePreferences {
  const result = defaultTablePreferences()
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result
  const stored = value as Record<string, unknown>
  if (stored.version !== undefined && stored.version !== 1) return result
  if (Array.isArray(stored.columns)) result.columns = optionalColumns.filter(c => (stored.columns as unknown[]).includes(c.value)).map(c => c.value)
  if (stored.density === 'comfortable') result.density = 'comfortable'
  if (typeof stored.pageSize === 'number' && [10, 20, 50, 100].includes(stored.pageSize)) result.pageSize = stored.pageSize
  return result
}
const state = reactive(parseTablePreferences(readPreference(tablePreferencesKey)))
export const tablePreferences = readonly(state)
export const tableSaveError = ref('')
export function updateTablePreferences(value: Partial<TablePreferences>): void {
  Object.assign(state, parseTablePreferences({ ...state, ...value }))
  tableSaveError.value = writePreference(tablePreferencesKey, state) ? '' : 'Table preferences apply for this session. Your browser could not save them.'
}
export function resetTablePreferences(): void { updateTablePreferences(defaultTablePreferences()) }
