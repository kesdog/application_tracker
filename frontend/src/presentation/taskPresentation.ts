import type { FollowUp, Task } from '../api'
import type { PresentationMeta } from './applicationPresentation'

export const taskStatusMeta: Record<Task['status'], PresentationMeta> = {
  PENDING: { label: 'Pending', tone: 'submitted', icon: 'pi pi-clock' },
  COMPLETED: { label: 'Completed', tone: 'successful', icon: 'pi pi-check' },
  CANCELLED: { label: 'Cancelled', tone: 'withdrawn', icon: 'pi pi-ban' },
}
export const followupStatusMeta: Record<FollowUp['status'], PresentationMeta> = {
  PREPARED: { label: 'Prepared', tone: 'submitted', icon: 'pi pi-file-edit' },
  READY: { label: 'Ready', tone: 'submitted', icon: 'pi pi-check-circle' },
  SENT: { label: 'Sent', tone: 'successful', icon: 'pi pi-check' },
}
export function urgencyMeta(dueAt: string | null, now = Date.now()): PresentationMeta {
  if (!dueAt) return { label: 'No due date', tone: 'neutral', icon: 'pi pi-clock' }
  const due = new Date(dueAt)
  if (due.getTime() < now) return { label: 'Overdue', tone: 'overdue', icon: 'pi pi-exclamation-circle' }
  if (due.toDateString() === new Date(now).toDateString()) return { label: 'Today', tone: 'dueSoon', icon: 'pi pi-clock' }
  if (due.getTime() - now <= 3 * 86400000) return { label: 'Due soon', tone: 'dueSoon', icon: 'pi pi-clock' }
  return { label: 'Scheduled', tone: 'neutral', icon: 'pi pi-calendar' }
}
