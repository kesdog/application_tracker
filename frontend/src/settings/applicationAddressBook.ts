import { computed, readonly, ref } from 'vue'
import { listApplications, type Application } from '../api'

export const suggestionFields = ['job_title', 'company', 'intermediary', 'location', 'contract_type', 'job_url', 'email_reference', 'contact_name', 'contact_email', 'phone_number', 'description', 'requirements', 'date_applied', 'deadline', 'followup_delay_days', 'max_followup_suggestions'] as const
export type SuggestionField = typeof suggestionFields[number]
const records = ref<Application[]>([])
export const addressBookError = ref('')
export const addressBookLoading = ref(false)
export const addressBook = readonly(records)
export function historyValues(applications: readonly Application[], field: SuggestionField): string[] {
  const seen = new Set<string>()
  return applications.flatMap(application => {
    const value = application[field]
    if (value === null || value === undefined || !String(value).trim()) return []
    const text = String(value).trim()
    const key = text.toLocaleLowerCase()
    if (seen.has(key)) return []
    seen.add(key)
    return [text]
  })
}
export const suggestions = computed(() => Object.fromEntries(suggestionFields.map(field => [field, historyValues(records.value, field)])) as Record<SuggestionField, string[]>)
export const savedContacts = computed(() => {
  const seen = new Set<string>()
  return records.value.filter(record => {
    if (!record.contact_email && !record.phone_number) return false
    const key = [record.company.toLocaleLowerCase(), record.contact_email?.toLocaleLowerCase(), record.phone_number].join('|')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).map(record => ({ value: record.id, label: `${record.contact_name ? `${record.contact_name} · ` : ''}${record.company} · ${record.contact_email || record.phone_number}`, record }))
})
export async function loadAddressBook(): Promise<void> {
  addressBookLoading.value = true
  addressBookError.value = ''
  try { records.value = await listApplications() }
  catch { addressBookError.value = 'Saved suggestions are unavailable. You can still enter a new application.' }
  finally { addressBookLoading.value = false }
}
export function rememberApplication(application: Application): void {
  records.value = [application, ...records.value.filter(record => record.id !== application.id)]
}
