import type { InterviewType } from '../api'
import type { PresentationMeta } from './applicationPresentation'
export const interviewTypeMeta: Record<InterviewType, PresentationMeta> = {
  PHONE: { label: 'Phone', tone: 'interview', icon: 'pi pi-phone' },
  HR: { label: 'HR', tone: 'interview', icon: 'pi pi-users' },
  TECHNICAL: { label: 'Technical', tone: 'interview', icon: 'pi pi-code' },
  ONSITE: { label: 'Onsite', tone: 'interview', icon: 'pi pi-building' },
  FINAL: { label: 'Final', tone: 'interview', icon: 'pi pi-flag' },
  OTHER: { label: 'Other', tone: 'interview', icon: 'pi pi-calendar' },
}
export const interviewTypeOptions = Object.entries(interviewTypeMeta).map(([value, meta]) => ({ value, label: meta.label }))
