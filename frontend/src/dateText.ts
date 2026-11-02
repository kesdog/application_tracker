import { t, intlLocale } from './i18n'
export function dateTimeText(value: string | null): string {
  return value ? new Date(value).toLocaleString(intlLocale.value, { dateStyle: 'medium', timeStyle: 'short' }) : t("No due date")
}

export function relativeDateText(value: string, prefix = ''): string {
  const target = new Date(value)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const targetDay = new Date(target.getFullYear(), target.getMonth(), target.getDate())
  const days = Math.round((targetDay.getTime() - today.getTime()) / 86400000)
  const time = target.toLocaleTimeString(intlLocale.value, { hour: '2-digit', minute: '2-digit' })
  if (days === 0) return t("{p0}today at {p1}", { p0: prefix, p1: time })
  if (days === 1) return t("{p0}tomorrow at {p1}", { p0: prefix, p1: time })
  if (days > 1 && days <= 7) return t("{p0}in {p1} days", { p0: prefix, p1: days })
  if (days === -1) return t("{p0}yesterday at {p1}", { p0: prefix, p1: time })
  if (days < -1 && days >= -7) return t("{p0}{p1} days ago", { p0: prefix, p1: Math.abs(days) })
  return `${prefix}${dateTimeText(value)}`
}

export function interviewTypeText(value: string): string {
  return t(value === 'HR' ? 'HR' : value.charAt(0) + value.slice(1).toLowerCase())
}
