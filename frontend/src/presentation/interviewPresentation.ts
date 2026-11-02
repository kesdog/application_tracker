import { t } from '../i18n'
import type { InterviewType } from '../api'
import type { PresentationMeta } from './applicationPresentation'
export const interviewTypeMeta: Record<InterviewType, PresentationMeta> = {
  PHONE: { get label() { return t("Phone") }, tone: 'interview', icon: 'pi pi-phone' },
  HR: { get label() { return t('HR') }, tone: 'interview', icon: 'pi pi-users' },
  TECHNICAL: { get label() { return t("Technical") }, tone: 'interview', icon: 'pi pi-code' },
  ONSITE: { get label() { return t("Onsite") }, tone: 'interview', icon: 'pi pi-building' },
  FINAL: { get label() { return t("Final") }, tone: 'interview', icon: 'pi pi-flag' },
  OTHER: { get label() { return t("Other") }, tone: 'interview', icon: 'pi pi-calendar' },
}
export const interviewTypeOptions = Object.entries(interviewTypeMeta).map(([value, meta]) => ({ value, get label() { return meta.label } }))
