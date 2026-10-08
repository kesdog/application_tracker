import type { Application } from '../api'
import type { AppearanceColor } from '../settings/appearanceDefaults'
import { jobSourceLabel } from '../applicationOptions'

export type Tone = AppearanceColor | 'neutral'
export interface PresentationMeta { label: string; tone: Tone; icon?: string }

export const applicationStatusMeta: Record<Application['status'], PresentationMeta> = {
  SUBMITTED: { label: 'Submitted', tone: 'submitted', icon: 'pi pi-send' },
  INTERVIEW: { label: 'Interview', tone: 'interview', icon: 'pi pi-calendar' },
  CLOSED: { label: 'Closed', tone: 'postingClosed', icon: 'pi pi-lock' },
}
export const applicationOutcomeMeta: Record<NonNullable<Application['outcome']>, PresentationMeta> = {
  SUCCESSFUL: { label: 'Successful', tone: 'successful', icon: 'pi pi-check' },
  UNSUCCESSFUL: { label: 'Unsuccessful', tone: 'unsuccessful', icon: 'pi pi-times' },
  WITHDRAWN: { label: 'Withdrawn', tone: 'withdrawn', icon: 'pi pi-sign-out' },
  JOB_CANCELLED: { label: 'Job cancelled', tone: 'cancelled', icon: 'pi pi-ban' },
  GHOSTED: { label: 'Ghosted', tone: 'ghosted', icon: 'pi pi-clock' },
}
export const postingStatusMeta: Record<Application['posting_status'], PresentationMeta> = {
  UNKNOWN: { label: 'Posting unknown', tone: 'neutral', icon: 'pi pi-question-circle' },
  LIVE: { label: 'Posting live', tone: 'live', icon: 'pi pi-external-link' },
  CLOSED: { label: 'Posting closed', tone: 'postingClosed', icon: 'pi pi-lock' },
}
export const remotePolicyMeta: Record<string, PresentationMeta> = {
  FULL_REMOTE: { label: 'Full remote', tone: 'neutral', icon: 'pi pi-home' },
  HYBRID: { label: 'Hybrid', tone: 'neutral', icon: 'pi pi-building' },
  IN_PERSON: { label: 'In person', tone: 'neutral', icon: 'pi pi-map-marker' },
}
export const contractOptions = [
  { value: 'CDI', label: 'Full time (CDI)' },
  { value: 'CDD', label: 'Fixed term (CDD)' },
  { value: 'PART_TIME', label: 'Part time (Temps partiel)' },
  { value: 'APPRENTICESHIP_INTERNSHIP', label: 'Apprenticeship / Internship (Alternance / Stage)' },
]
export const contractLabel = (value: string | null) => contractOptions.find(option => option.value === value)?.label ?? value ?? '—'
export const sourceLabel = jobSourceLabel
export const statusOptions = Object.entries(applicationStatusMeta).map(([value, meta]) => ({ value, label: meta.label }))
export const outcomeOptions = Object.entries(applicationOutcomeMeta).map(([value, meta]) => ({ value, label: meta.label }))

export function applicationRowClass(application: Application, overdueIds: ReadonlySet<string>): string {
  if (overdueIds.has(application.id)) return 'row-overdue'
  return application.status === 'CLOSED' ? 'row-closed' : ''
}
