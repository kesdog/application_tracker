import { afterEach, expect, it, vi } from 'vitest'
import { interviewTypeText, relativeDateText } from '../../src/dateText'
afterEach(() => vi.useRealTimers())

it('formats interview labels and near-term dates for upcoming work', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-09-25T09:00:00Z'))
  expect(interviewTypeText('TECHNICAL')).toBe('Technical')
  expect(relativeDateText('2026-09-26T14:00:00Z')).toMatch(/^tomorrow at /)
  expect(relativeDateText('2026-09-28T14:00:00Z', 'due ')).toBe('due in 3 days')
})
