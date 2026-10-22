// @vitest-environment jsdom
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import FollowUpTarget from '../../src/components/followups/FollowUpTarget.vue'
import { followupTargetStatus } from '../../src/presentation/followupTargets'
import type { Application, FollowUp, FollowUpTargetStatus } from '../../src/api'

it('renders all four envelope states with distinct classes and descriptive accessible labels', () => {
  for (const status of ['UNKNOWN', 'POTENTIAL', 'CONFIRMED', 'SENT'] as FollowUpTargetStatus[]) {
    const wrapper = mount(FollowUpTarget, { props: { status } })
    expect(wrapper.classes()).toContain(`target-${status.toLowerCase()}`)
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toBe(wrapper.attributes('title'))
    expect(wrapper.find('.pi-envelope').exists()).toBe(true)
    wrapper.unmount()
  }
})

it('keeps a queue item independent of the application sent history and distinguishes phone calls', () => {
  const app = { followup_target_status: 'SENT', has_potential_recipients: false } as Application
  const followup = { channel: 'EMAIL', status: 'PREPARED', recipient_email: null } as FollowUp
  expect(followupTargetStatus(app)).toBe('SENT')
  expect(followupTargetStatus(app, followup)).toBe('UNKNOWN')
  expect(followupTargetStatus({ ...app, has_potential_recipients: true }, followup)).toBe('POTENTIAL')
  expect(followupTargetStatus(app, { ...followup, recipient_email: 'hr@example.com' })).toBe('CONFIRMED')
  expect(followupTargetStatus(app, { ...followup, status: 'SENT' })).toBe('SENT')
  expect(followupTargetStatus(app, { ...followup, channel: 'PHONE', status: 'SENT' })).toBeNull()
})
