import type { Application, FollowUp } from '../api'
import type { FollowUpTargetStatus } from '../api'

export const followupTargetLabels: Record<FollowUpTargetStatus, string> = {
  UNKNOWN: 'Follow-up target unknown',
  POTENTIAL: 'Potential follow-up targets · review needed',
  CONFIRMED: 'Follow-up recipient confirmed',
  SENT: 'Follow-up sent',
}

export function followupTargetStatus(application: Application, followup?: FollowUp): FollowUpTargetStatus | null {
  if (!followup) return application.followup_target_status ?? (application.contact_email ? 'CONFIRMED' : 'UNKNOWN')
  if (followup.channel === 'PHONE') return null
  if (followup.status === 'SENT') return 'SENT'
  if (followup.recipient_email?.trim()) return 'CONFIRMED'
  return application.has_potential_recipients ? 'POTENTIAL' : 'UNKNOWN'
}
