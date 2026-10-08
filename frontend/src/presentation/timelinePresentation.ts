import type { ActorType } from '../api'
import type { PresentationMeta } from './applicationPresentation'
export const actorLabels: Record<ActorType, string> = { HUMAN: 'Human', AGENT: 'Agent', SYSTEM: 'System' }
const timelineMeta: Record<string, PresentationMeta> = {
  APPLICATION_CREATED: { label: 'Application created', tone: 'submitted', icon: 'pi pi-plus' },
  APPLICATION_SUBMITTED: { label: 'Application submitted', tone: 'submitted', icon: 'pi pi-send' },
  STATUS_CHANGED: { label: 'Status changed', tone: 'submitted', icon: 'pi pi-arrow-right' },
  OUTCOME_CHANGED: { label: 'Outcome changed', tone: 'neutral', icon: 'pi pi-flag' },
  NOTE_ADDED: { label: 'Note added', tone: 'neutral', icon: 'pi pi-file-edit' },
  NOTE_CHANGED: { label: 'Note changed', tone: 'neutral', icon: 'pi pi-file-edit' },
  TASK_CREATED: { label: 'Task created', tone: 'submitted', icon: 'pi pi-list' },
  TASK_CHANGED: { label: 'Task changed', tone: 'submitted', icon: 'pi pi-list' },
  TASK_COMPLETED: { label: 'Task completed', tone: 'successful', icon: 'pi pi-check' },
  FOLLOWUP_CREATED: { label: 'Follow-up created', tone: 'submitted', icon: 'pi pi-send' },
  FOLLOWUP_DRAFTED: { label: 'Follow-up drafted', tone: 'submitted', icon: 'pi pi-file-edit' },
  FOLLOWUP_SENT: { label: 'Follow-up sent', tone: 'successful', icon: 'pi pi-check' },
  FOLLOWUP_CHANGED: { label: 'Follow-up changed', tone: 'submitted', icon: 'pi pi-send' },
  INTERVIEW_CREATED: { label: 'Interview created', tone: 'interview', icon: 'pi pi-calendar' },
  INTERVIEW_CHANGED: { label: 'Interview changed', tone: 'interview', icon: 'pi pi-calendar' },
  INTERVIEW_DELETED: { label: 'Interview deleted', tone: 'neutral', icon: 'pi pi-calendar-times' },
  UNDO: { label: 'Change undone', tone: 'neutral', icon: 'pi pi-undo' },
  MANUAL: { label: 'Email activity', tone: 'neutral', icon: 'pi pi-envelope' },
}
export const timelineEventMeta = (type: string): PresentationMeta => timelineMeta[type] ?? { label: 'Activity', tone: 'neutral', icon: 'pi pi-pencil' }
