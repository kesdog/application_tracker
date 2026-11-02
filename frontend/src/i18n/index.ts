import { computed, readonly, ref } from 'vue'
import { readPreference, writePreference } from '../settings/localPreferences'
import french from './fr.json'

export type Locale = 'en' | 'fr'
export const localeStorageKey = 'application-tracker:language'
const selected = ref<Locale>('en')
export const locale = readonly(selected)
export const intlLocale = computed(() => selected.value === 'fr' ? 'fr-FR' : 'en-GB')
export const languageSaveError = ref('')
export const languages = [{ value: 'en', label: 'English' }, { value: 'fr', label: 'Français' }] as const
const catalog: Record<string, string> = french
const enumMessages: Record<string, string> = {
  submitted: 'Submitted', successful: 'Successful', unsuccessful: 'Unsuccessful', withdrawn: 'Withdrawn', job_cancelled: 'Job cancelled', ghosted: 'Ghosted', full_remote: 'Full remote', hybrid: 'Hybrid', in_person: 'In person', cdi: 'Full time (CDI)', cdd: 'Fixed term (CDD)', part_time: 'Part time (Temps partiel)', apprenticeship_internship: 'Apprenticeship / Internship (Alternance / Stage)',
  prepared: 'Prepared', ready: 'Ready', sent: 'Sent', pending: 'Pending', completed: 'Completed', cancelled: 'Cancelled',
  email: 'Email', phone: 'Phone', both: 'Email + phone', general: 'General', assessment: 'Assessment', email_draft: 'Email draft', interview: 'Interview', agent: 'Agent',
  granted: 'Granted', denied: 'Denied', default: 'Default', unavailable: 'Unavailable', enabled: 'Enabled', accepted: 'Accepted', failed: 'Failed', delivered: 'Delivered', expired: 'Expired',
  revised_message: 'Revised message', 'revised message': 'Revised message', mailbox_draft_created: 'Mailbox draft created', 'mailbox draft created': 'Mailbox draft created', skipped: 'Skipped', needs_clarification: 'Needs clarification', 'needs clarification': 'Needs clarification', failure: 'Failure',
  active: 'Active', running: 'Running', queued: 'Queued', idle: 'Idle', partial: 'Partial', connected: 'Connected', disconnected: 'Disconnected', unknown: 'Unknown', live: 'Live', closed: 'Closed',
}
type Params = Record<string, unknown>

/** English source messages are stable catalog keys. Values never pass through HTML. */
export function t(message: string, params: Params = {}): string {
  const translated = selected.value === 'fr' ? catalog[message] ?? message : message
  return translated.replace(/\{(p\d+)\}/g, (token, key) => key in params ? String(params[key] ?? '') : token)
}

export function fieldLabel(key: string): string {
  const label = key.replaceAll('_', ' ')
  return t(label.charAt(0).toUpperCase() + label.slice(1))
}

// Server messages can contain names, counts and limits. Match complete messages,
// preserving their data, rather than translating substrings of user-authored text.
function messagePattern(key: string) {
  const names: string[] = []
  const escaped = key.split(/(\{p\d+\})/).map(part => {
    if (/^\{p\d+\}$/.test(part)) { names.push(part.slice(1, -1)); return '([\\s\\S]*?)' }
    return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }).join('')
  return { names, pattern: new RegExp('^' + escaped + '$') }
}
const patterns = Object.keys(catalog).filter(key => /\{p\d+\}/.test(key)).map(key => ({ key, ...messagePattern(key) }))
const reverseCatalog = Object.fromEntries(Object.entries(catalog).map(([key, value]) => [value, key]))
const reversePatterns = Object.entries(catalog).filter(([key]) => /\{p\d+\}/.test(key)).map(([key, value]) => ({ key, ...messagePattern(value) }))
function canonicalMessage(message: string): string {
  if (Object.hasOwn(catalog, message)) return message
  if (reverseCatalog[message]) return reverseCatalog[message]!
  for (const { key, names, pattern } of reversePatterns) {
    const match = message.match(pattern)
    if (match) {
      const params = Object.fromEntries(names.map((name, i) => [name, match[i + 1]]))
      return key.replace(/\{(p\d+)\}/g, (token, name) => params[name] ?? token)
    }
  }
  return message
}
export function messageText(message: string): string {
  message = canonicalMessage(message)
  if (!message || selected.value === 'en') return message
  if (catalog[message]) return catalog[message]!
  const enumMessage = enumMessages[message.toLowerCase()]
  if (enumMessage) return t(enumMessage)
  for (const { key, names, pattern } of patterns) {
    const match = message.match(pattern)
    if (match) return t(key, Object.fromEntries(names.map((name, i) => [name, match[i + 1]])))
  }
  return message
}

/** Unknown provider/browser diagnostics get a localized fallback. Keep raw errors in the API layer. */
export function errorText(message: string): string {
  message = canonicalMessage(message)
  if (selected.value === 'en' || !message) return message
  if (message.startsWith('Value error, ')) return errorText(message.slice(13))
  const translated = messageText(message)
  if (translated !== message || Object.hasOwn(catalog, message)) return translated
  if (/abort|timeout|timed out/i.test(message)) return t('The request timed out. Try again.')
  if (/fetch|network|connection/i.test(message)) return t('The connection was interrupted. Check your connection and try again.')
  // Already localized errors can have been generated by t() in event handlers.
  if (Object.values(catalog).includes(message)) return message
  return t('This action could not be completed. Try again.')
}

export function setLocale(value: string): void {
  if (value !== 'en' && value !== 'fr') return
  selected.value = value
  if (typeof document !== 'undefined') { document.documentElement.lang = value; document.title = t('Application Tracker — My workspace') }
  languageSaveError.value = writePreference(localeStorageKey, value) ? '' : 'Language is applied for this session. Your browser could not save it for the next visit.'
}
export function loadLocale(): void {
  const stored = readPreference(localeStorageKey)
  selected.value = stored === 'fr' ? 'fr' : 'en'
  if (typeof document !== 'undefined') { document.documentElement.lang = selected.value; document.title = t('Application Tracker — My workspace') }
}
