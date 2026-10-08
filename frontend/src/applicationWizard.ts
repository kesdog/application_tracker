import type { ApplicationCreate } from './api'
import { detectJobSource, type ContactType, type JobSource, type RemotePolicy } from './applicationOptions'

export function blankApplicationDraft() {
  const now = new Date()
  return {
    job_title: '', company: '', intermediary: '', date_applied: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`,
    job_url: '', email_reference: '', contact_type: 'EMAIL' as ContactType, contact_name: '', contact_email: '', phone_number: '',
    location: '', remote_policy: null as RemotePolicy | null, contract_type: '', source: 'OTHER' as JobSource,
    description: '', requirements: '', deadline: '', deadline_kind: 'APPLICATION_CLOSING' as 'APPLICATION_CLOSING' | 'FIRST_ROUND',
    followup_delay_days: null as number | null | '', max_followup_suggestions: null as number | null | '',
  }
}
export type ApplicationDraft = ReturnType<typeof blankApplicationDraft>
export interface WizardOptions { intermediary: boolean; contact: boolean; extraContact: boolean; deadline: boolean; notes: boolean; followups: boolean }
export const blankWizardOptions = (): WizardOptions => ({ intermediary: false, contact: false, extraContact: false, deadline: false, notes: false, followups: false })
export function validCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(value + 'T12:00:00Z')
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
}
export function wizardErrors(step: number, draft: ApplicationDraft, options: WizardOptions): Record<string, string> {
  const errors: Record<string, string> = {}
  if (step === 1) {
    if (!draft.job_title.trim()) errors.job_title = 'Enter the job title.'
    if (!draft.company.trim()) errors.company = 'Enter the employer or “Employer not disclosed”.'
    if (!validCalendarDate(draft.date_applied)) errors.date_applied = 'Choose a valid application date.'
  }
  if (step === 2) {
    if (!draft.job_url.trim() && !draft.email_reference.trim()) errors.job_url = 'Provide a posting URL or an email reference.'
    if (draft.job_url.trim()) {
      try { if (!['http:', 'https:'].includes(new URL(draft.job_url.trim()).protocol)) throw new Error() }
      catch { errors.job_url = 'Enter a complete http or https posting URL.' }
      if (['LINKEDIN', 'INDEED'].includes(draft.source) && detectJobSource(draft.job_url) !== draft.source) errors.job_url = 'Use a direct posting URL on the selected LinkedIn or Indeed board.'
    }
    if (options.deadline && !validCalendarDate(draft.deadline)) errors.deadline = 'Choose a valid deadline date.'
  }
  if (step === 3) {
    if (options.contact) {
      if (draft.contact_type === 'EMAIL' && !draft.contact_email.trim()) errors.contact_email = 'Enter the contact email address.'
      if (draft.contact_type === 'PHONE' && !draft.phone_number.trim()) errors.phone_number = 'Enter the contact phone number.'
    }
    if (options.followups) {
      for (const [field, max] of [['followup_delay_days', 3650], ['max_followup_suggestions', 100]] as const) {
        const value = draft[field]
        if (value !== null && value !== '' && (!Number.isInteger(value) || value < 0 || value > max)) errors[field] = `Enter a whole number from 0 to ${max}.`
      }
    }
  }
  return errors
}
export function applicationPayload(draft: ApplicationDraft, options: WizardOptions): ApplicationCreate {
  const text = (value: string) => value.trim() || null
  return {
    job_title: draft.job_title.trim(), company: draft.company.trim(), date_applied: draft.date_applied,
    intermediary: options.intermediary ? text(draft.intermediary) : null,
    job_url: text(draft.job_url), email_reference: text(draft.email_reference),
    contact_type: options.contact ? draft.contact_type : 'EMAIL', contact_name: options.contact ? text(draft.contact_name) : null,
    contact_email: options.contact && (draft.contact_type === 'EMAIL' || options.extraContact) ? text(draft.contact_email) : null,
    phone_number: options.contact && (draft.contact_type === 'PHONE' || options.extraContact) ? text(draft.phone_number) : null,
    location: text(draft.location), remote_policy: draft.remote_policy, contract_type: text(draft.contract_type), source: draft.source,
    deadline: options.deadline ? draft.deadline : null, deadline_kind: options.deadline ? draft.deadline_kind : null,
    description: options.notes ? text(draft.description) : null, requirements: options.notes ? text(draft.requirements) : null,
    followup_delay_days: options.followups && draft.followup_delay_days !== '' ? draft.followup_delay_days : null,
    max_followup_suggestions: options.followups && draft.max_followup_suggestions !== '' ? draft.max_followup_suggestions : null,
  }
}
