import { t } from '../i18n'
import type { FollowUp, Task } from '../api'
import type { PresentationMeta } from './applicationPresentation'

export const taskStatusMeta: Record<Task['status'], PresentationMeta> = {
  PENDING: { get label() { return t("Pending") }, tone: 'submitted', icon: 'pi pi-clock' },
  COMPLETED: { get label() { return t("Completed") }, tone: 'successful', icon: 'pi pi-check' },
  CANCELLED: { get label() { return t("Cancelled") }, tone: 'withdrawn', icon: 'pi pi-ban' },
}
export const followupStatusMeta: Record<FollowUp['status'], PresentationMeta> = {
  PREPARED: { get label() { return t("Prepared") }, tone: 'submitted', icon: 'pi pi-file-edit' },
  READY: { get label() { return t("Ready") }, tone: 'submitted', icon: 'pi pi-check-circle' },
  SENT: { get label() { return t("Sent") }, tone: 'successful', icon: 'pi pi-check' },
}
export function urgencyMeta(dueAt: string | null, now = Date.now()): PresentationMeta {
  if (!dueAt) return { get label() { return t("No due date") }, tone: 'neutral', icon: 'pi pi-clock' }
  const due = new Date(dueAt)
  if (due.getTime() < now) return { get label() { return t("Overdue") }, tone: 'overdue', icon: 'pi pi-exclamation-circle' }
  if (due.toDateString() === new Date(now).toDateString()) return { get label() { return t("Today") }, tone: 'dueSoon', icon: 'pi pi-clock' }
  if (due.getTime() - now <= 3 * 86400000) return { get label() { return t("Due soon") }, tone: 'dueSoon', icon: 'pi pi-clock' }
  return { get label() { return t("Scheduled") }, tone: 'neutral', icon: 'pi pi-calendar' }
}
