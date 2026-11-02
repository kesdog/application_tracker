import { t } from '../i18n'
import type { Application } from '../api'
import type { AppearanceColor } from '../settings/appearanceDefaults'
import { jobSourceLabel } from '../applicationOptions'

export type Tone = AppearanceColor | 'neutral'
export interface PresentationMeta { label: string; tone: Tone; icon?: string }

export const applicationStatusMeta: Record<Application['status'], PresentationMeta> = {
  SUBMITTED: { get label() { return t("Submitted") }, tone: 'submitted', icon: 'pi pi-file-check' },
  INTERVIEW: { get label() { return t("Interview") }, tone: 'interview', icon: 'pi pi-calendar' },
  CLOSED: { get label() { return t("Closed") }, tone: 'postingClosed', icon: 'pi pi-lock' },
}
export const applicationOutcomeMeta: Record<NonNullable<Application['outcome']>, PresentationMeta> = {
  SUCCESSFUL: { get label() { return t("Successful") }, tone: 'successful', icon: 'pi pi-check' },
  UNSUCCESSFUL: { get label() { return t("Unsuccessful") }, tone: 'unsuccessful', icon: 'pi pi-times' },
  WITHDRAWN: { get label() { return t("Withdrawn") }, tone: 'withdrawn', icon: 'pi pi-sign-out' },
  JOB_CANCELLED: { get label() { return t("Job cancelled") }, tone: 'cancelled', icon: 'pi pi-ban' },
  GHOSTED: { get label() { return t("Ghosted") }, tone: 'ghosted', icon: 'pi pi-clock' },
}
export const postingStatusMeta: Record<Application['posting_status'], PresentationMeta> = {
  UNKNOWN: { get label() { return t("Posting unknown") }, tone: 'neutral', icon: 'pi pi-question-circle' },
  LIVE: { get label() { return t("Posting live") }, tone: 'live', icon: 'pi pi-external-link' },
  CLOSED: { get label() { return t("Posting closed") }, tone: 'postingClosed', icon: 'pi pi-lock' },
}
export const remotePolicyMeta: Record<string, PresentationMeta> = {
  FULL_REMOTE: { get label() { return t("Full remote") }, tone: 'neutral', icon: 'pi pi-home' },
  HYBRID: { get label() { return t("Hybrid") }, tone: 'neutral', icon: 'pi pi-building' },
  IN_PERSON: { get label() { return t("In person") }, tone: 'neutral', icon: 'pi pi-map-marker' },
}
export const contractOptions = [
  { value: 'CDI', get label() { return t("Full time (CDI)") } },
  { value: 'CDD', get label() { return t("Fixed term (CDD)") } },
  { value: 'PART_TIME', get label() { return t("Part time (Temps partiel)") } },
  { value: 'APPRENTICESHIP_INTERNSHIP', get label() { return t("Apprenticeship / Internship (Alternance / Stage)") } },
]
export const contractLabel = (value: string | null) => contractOptions.find(option => option.value === value)?.label ?? value ?? '—'
// Imported titles can repeat contract metadata at either edge. Keep role words intact.
export function positionLabel(title: string): string {
  const contract = '(?:CDI|CDD|full[ -]time|part[ -]time|temps partiel|fixed[ -]term|alternance|apprenticeship|internship|stage(?: \\d+ mois(?: ou alternance)?)?)'
  const prefix = new RegExp(`^\\s*(?:\\(${contract}\\)|\\[${contract}\\]|${contract})(?:\\s*[-–—:|]\\s*|\\s+)`, 'i')
  const suffix = new RegExp(`(?:\\s*[-–—|]\\s*${contract}|\\s+${contract}|\\s*\\(${contract}\\)|\\s*\\[${contract}\\])\\s*$`, 'i')
  let result = title
  let prior = ''
  while (result !== prior) { prior = result; result = result.replace(prefix, '').replace(suffix, '').trim() }
  return result || title
}
export const sourceLabel = jobSourceLabel
export const statusOptions = Object.entries(applicationStatusMeta).map(([value, meta]) => ({ value, get label() { return meta.label } }))
export const outcomeOptions = Object.entries(applicationOutcomeMeta).map(([value, meta]) => ({ value, get label() { return meta.label } }))

export function applicationRowClass(application: Application, overdueIds: ReadonlySet<string>): string {
  if (overdueIds.has(application.id)) return 'row-overdue'
  return application.status === 'CLOSED' ? 'row-closed' : ''
}
