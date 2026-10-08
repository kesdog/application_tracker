import type { DashboardData, UpcomingItem } from '../api'
import type { PresentationMeta } from './applicationPresentation'

export interface NextAction extends PresentationMeta { dueAt: string | null; title: string }
const byDate = (a: UpcomingItem, b: UpcomingItem) => Date.parse(a.due_at) - Date.parse(b.due_at)

export function nextApplicationAction(id: string, dashboard: DashboardData | null, now = Date.now()): NextAction | null {
  if (!dashboard) return null
  const belongs = (item: UpcomingItem) => item.application.id === id
  const overdue = dashboard.overdue_followups.filter(belongs).sort(byDate)[0]
  if (overdue) return { label: 'Overdue follow-up', title: overdue.title, tone: 'overdue', icon: 'pi pi-exclamation-circle', dueAt: overdue.due_at }
  const upcoming = dashboard.upcoming.filter(belongs).filter(item => item.kind !== 'INTERVIEW' || Date.parse(item.due_at) >= now).sort(byDate)
  const interview = upcoming.find(item => item.kind === 'INTERVIEW')
  if (interview) return { label: 'Interview', title: interview.title, tone: 'interview', icon: 'pi pi-calendar', dueAt: interview.due_at }
  const followup = [...dashboard.due_followups.filter(belongs), ...upcoming.filter(item => item.kind === 'FOLLOWUP')].sort(byDate)[0]
  if (followup) return { label: 'Follow-up', title: followup.title, tone: 'dueSoon', icon: 'pi pi-send', dueAt: followup.due_at }
  const task = upcoming.find(item => item.kind === 'TASK')
  return task ? { label: 'Pending task', title: task.title, tone: Date.parse(task.due_at) < now ? 'overdue' : 'neutral', icon: 'pi pi-list-check', dueAt: task.due_at } : null
}
