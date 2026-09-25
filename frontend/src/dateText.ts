export function dateTimeText(value: string | null): string {
  return value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'No due date'
}

export function relativeDateText(value: string, prefix = ''): string {
  const target = new Date(value)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const targetDay = new Date(target.getFullYear(), target.getMonth(), target.getDate())
  const days = Math.round((targetDay.getTime() - today.getTime()) / 86400000)
  const time = target.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (days === 0) return `${prefix}today at ${time}`
  if (days === 1) return `${prefix}tomorrow at ${time}`
  if (days > 1 && days <= 7) return `${prefix}in ${days} days`
  if (days === -1) return `${prefix}yesterday at ${time}`
  if (days < -1 && days >= -7) return `${prefix}${Math.abs(days)} days ago`
  return `${prefix}${dateTimeText(value)}`
}

export function interviewTypeText(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase()
}
