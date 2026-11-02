import { t } from '../i18n'
import type { ActorType } from '../api'
import type { PresentationMeta } from './applicationPresentation'
export const actorLabels: Record<ActorType, string> = { HUMAN: 'Human', AGENT: 'Agent', SYSTEM: 'System' }
const timelineMeta: Record<string, PresentationMeta> = {
  APPLICATION_CREATED: { get label() { return t("Application created") }, tone: 'submitted', icon: 'pi pi-plus' },
  APPLICATION_SUBMITTED: { get label() { return t("Application submitted") }, tone: 'submitted', icon: 'pi pi-file-check' },
  APPLICATION_UPDATED: { get label() { return t("Application updated") }, tone: 'neutral', icon: 'pi pi-file-edit' },
  POSTING_STATUS_CHANGED: { get label() { return t("Posting status changed") }, tone: 'neutral', icon: 'pi pi-link' },
  STATUS_CHANGED: { get label() { return t("Status changed") }, tone: 'submitted', icon: 'pi pi-arrow-right' },
  OUTCOME_CHANGED: { get label() { return t("Outcome changed") }, tone: 'neutral', icon: 'pi pi-flag' },
  NOTE_ADDED: { get label() { return t("Note added") }, tone: 'neutral', icon: 'pi pi-file-edit' },
  NOTE_CHANGED: { get label() { return t("Note changed") }, tone: 'neutral', icon: 'pi pi-file-edit' },
  TASK_CREATED: { get label() { return t("Task created") }, tone: 'submitted', icon: 'pi pi-list' },
  TASK_CHANGED: { get label() { return t("Task changed") }, tone: 'submitted', icon: 'pi pi-list' },
  TASK_COMPLETED: { get label() { return t("Task completed") }, tone: 'successful', icon: 'pi pi-check' },
  FOLLOWUP_CREATED: { get label() { return t("Follow-up created") }, tone: 'submitted', icon: 'pi pi-send' },
  FOLLOWUP_DRAFTED: { get label() { return t("Follow-up drafted") }, tone: 'submitted', icon: 'pi pi-file-edit' },
  FOLLOWUP_SENT: { get label() { return t("Follow-up sent") }, tone: 'successful', icon: 'pi pi-check' },
  FOLLOWUP_CHANGED: { get label() { return t("Follow-up changed") }, tone: 'submitted', icon: 'pi pi-send' },
  INTERVIEW_CREATED: { get label() { return t("Interview created") }, tone: 'interview', icon: 'pi pi-calendar' },
  INTERVIEW_CHANGED: { get label() { return t("Interview changed") }, tone: 'interview', icon: 'pi pi-calendar' },
  INTERVIEW_DELETED: { get label() { return t("Interview deleted") }, tone: 'neutral', icon: 'pi pi-calendar-times' },
  UNDO: { get label() { return t("Change undone") }, tone: 'neutral', icon: 'pi pi-undo' },
  MANUAL: { get label() { return t("Email activity") }, tone: 'neutral', icon: 'pi pi-envelope' },
}
export const timelineEventMeta = (type: string): PresentationMeta => timelineMeta[type] ?? { get label() { return t("Activity") }, tone: 'neutral', icon: 'pi pi-pencil' }
