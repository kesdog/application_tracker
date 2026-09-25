import { afterEach, expect, it, vi } from 'vitest'
import { createInterview, deleteInterview, getInterviewContext, listApplicationInterviews, listInterviews, listTasks, updateInterview } from './api'
import { interviewTypeText, relativeDateText } from './dateText'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

const input = {
  type: 'TECHNICAL' as const, scheduled_at: '2026-09-28T12:00:00Z', duration: 60,
  location: null, meeting_url: null, interviewer: 'Sam', email_reference: null, notes: null, result: null,
}

it('uses application-scoped interview create, update, list and delete routes', async () => {
  const fetchMock = vi.fn().mockImplementation((_url: string, options?: RequestInit) =>
    Promise.resolve(new Response(options?.method === 'DELETE' ? null : '{}', { status: options?.method === 'POST' ? 201 : options?.method === 'DELETE' ? 204 : 200 })))
  vi.stubGlobal('fetch', fetchMock)
  await listApplicationInterviews('app one')
  await createInterview('app one', input)
  await updateInterview('app one', 'interview one', { result: 'Advanced' })
  await deleteInterview('app one', 'interview one')
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/applications/app%20one/interviews', expect.objectContaining({ cache: 'no-store' }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/applications/app%20one/interviews', expect.objectContaining({ method: 'POST', body: JSON.stringify(input) }))
  expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/applications/app%20one/interviews/interview%20one', expect.objectContaining({ method: 'PATCH', body: '{"result":"Advanced"}' }))
  expect(fetchMock).toHaveBeenNthCalledWith(4, '/api/applications/app%20one/interviews/interview%20one', expect.objectContaining({ method: 'DELETE' }))
})

it('loads global interviews, tasks, and interview context', async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('[]')))
  vi.stubGlobal('fetch', fetchMock)
  await listInterviews(); await listTasks(); await getInterviewContext('abc/123')
  expect(fetchMock.mock.calls.map(call => call[0])).toEqual(['/api/interviews', '/api/tasks', '/api/interviews/abc%2F123/context'])
})

it('formats interview labels and near-term dates for upcoming work', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-09-25T09:00:00Z'))
  expect(interviewTypeText('TECHNICAL')).toBe('Technical')
  expect(relativeDateText('2026-09-26T14:00:00Z')).toMatch(/^tomorrow at /)
  expect(relativeDateText('2026-09-28T14:00:00Z', 'due ')).toBe('due in 3 days')
})
