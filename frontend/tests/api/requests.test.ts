import { afterEach, expect, it, vi } from 'vitest'
import * as api from '../../src/api'

afterEach(() => vi.unstubAllGlobals())

it('reads the feature endpoints with encoded identifiers, filters and no caching', async () => {
  // All reads share request(); keep one route contract table and one fetch setup.
  const payload = { marker: 'server response' }
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(payload))))
  vi.stubGlobal('fetch', fetch)
  const reads: [string, () => Promise<unknown>][] = [
    ['/api/applications', () => api.listApplications()],
    ['/api/applications?q=python+engineer&status=INTERVIEW&date_from=2026-09-01', () => api.listApplications({ q: 'python engineer', status: 'INTERVIEW', company: '', date_from: '2026-09-01' })],
    ['/api/applications/app%2Fone', () => api.getApplication('app/one')],
    ['/api/applications/app%2Fone/work', () => api.getWork('app/one')],
    ['/api/applications/app%2Fone/timeline', () => api.getTimeline('app/one')],
    ['/api/applications/app%2Fone/documents', () => api.listDocuments('app/one')],
    ['/api/applications/app%2Fone/interviews', () => api.listApplicationInterviews('app/one')],
    ['/api/interviews', () => api.listInterviews()],
    ['/api/tasks', () => api.listTasks()],
    ['/api/interviews/abc%2F123/context', () => api.getInterviewContext('abc/123')],
    ['/api/dashboard', () => api.getDashboard()],
    ['/api/settings/agent', () => api.getAgentSettings()],
  ]
  for (const [url, read] of reads) {
    await expect(read(), url).resolves.toEqual(payload)
    expect(fetch, url).toHaveBeenLastCalledWith(url, expect.objectContaining({ cache: 'no-store' }))
  }
})

it('writes the feature routes with exact JSON, explicit nulls and empty DELETE responses', async () => {
  const fetch = vi.fn().mockImplementation((_url: string, options?: RequestInit) => Promise.resolve(
    new Response(options?.method === 'DELETE' ? null : '{"id":"saved","token":"new-token"}', { status: options?.method === 'DELETE' ? 204 : 200 }),
  ))
  vi.stubGlobal('fetch', fetch)
  const application = { job_title: 'Engineer', company: 'Example', date_applied: '2026-09-18', job_url: null, email_reference: 'Message 123', phone_number: null }
  const permissions = { read: true, create: true, edit: false, draft: false, tasks: false, interviews: false }
  const interview: api.InterviewInput = { type: 'TECHNICAL', scheduled_at: '2026-09-28T12:00:00Z', duration: 60, location: null, meeting_url: null, interviewer: 'Sam', email_reference: null, notes: null, result: null }
  const writes: [string, string, unknown, () => Promise<unknown>][] = [
    ['/api/applications', 'POST', application, () => api.createApplication(application)],
    ['/api/applications/app', 'PATCH', { status: 'INTERVIEW', outcome: null }, () => api.updateApplication('app', { status: 'INTERVIEW', outcome: null })],
    ['/api/applications/app/notes', 'POST', { content: 'Assessment', type: 'ASSESSMENT' }, () => api.createNote('app', { content: 'Assessment', type: 'ASSESSMENT' })],
    ['/api/applications/app/notes/note', 'PATCH', { content: 'Updated', type: 'GENERAL' }, () => api.updateNote('app', 'note', { content: 'Updated', type: 'GENERAL' })],
    ['/api/applications/app/tasks', 'POST', { title: 'Prepare', description: null, due_at: '2026-09-25T12:00:00Z' }, () => api.createTask('app', { title: 'Prepare', description: null, due_at: '2026-09-25T12:00:00Z' })],
    ['/api/applications/app/tasks/task', 'PATCH', { status: 'COMPLETED' }, () => api.updateTask('app', 'task', { status: 'COMPLETED' })],
    ['/api/applications/app/followups', 'POST', { due_at: null, template_reference: null, channel: 'EMAIL' }, () => api.createFollowUp('app', { due_at: null, template_reference: null, channel: 'EMAIL' })],
    ['/api/applications/app/followups/message', 'PATCH', { status: 'SENT' }, () => api.updateFollowUp('app', 'message', { status: 'SENT' })],
    ['/api/applications/app%20one/interviews', 'POST', interview, () => api.createInterview('app one', interview)],
    ['/api/applications/app%20one/interviews/interview%20one', 'PATCH', { result: 'Advanced' }, () => api.updateInterview('app one', 'interview one', { result: 'Advanced' })],
    ['/api/applications/app%20one/interviews/interview%20one', 'DELETE', undefined, () => api.deleteInterview('app one', 'interview one')],
    ['/api/applications/app/undo', 'POST', undefined, () => api.undoLastChange('app')],
    ['/api/applications/app', 'DELETE', undefined, () => api.deleteApplication('app')],
    ['/api/settings/agent/token', 'POST', undefined, () => api.regenerateAgentToken()],
    ['/api/settings/agent/permissions', 'PUT', permissions, () => api.saveAgentPermissions(permissions)],
  ]
  for (const [url, method, body, write] of writes) {
    await expect(write(), url).resolves.toEqual(method === 'DELETE' ? undefined : { id: 'saved', token: 'new-token' })
    expect(fetch, url).toHaveBeenLastCalledWith(url, expect.objectContaining({ method, ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }) }))
  }
})

it('surfaces both validation payload shapes and non-JSON proxy failures', async () => {
  for (const [body, status, message] of [
    [JSON.stringify({ detail: [{ msg: 'Provide a job URL or an email reference' }] }), 422, 'Provide a job URL or an email reference'],
    ['{"detail":"To reopen this application, explicitly clear its outcome"}', 422, 'explicitly clear its outcome'],
    ['Unavailable', 502, 'Request failed (502)'],
  ] as const) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status })))
    await expect(api.listApplications()).rejects.toThrow(message)
  }
})

it('uploads multipart documents without forcing a JSON content type', async () => {
  const saved = { id: 'document-1', filename: 'cv.pdf' }
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(saved), { status: 201 }))
  vi.stubGlobal('fetch', fetch)
  const file = new File(['cv'], 'cv.pdf', { type: 'application/pdf' })
  await expect(api.createDocument('application/id', { document_type: 'CV', file })).resolves.toEqual(saved)
  const [url, options] = fetch.mock.calls[0]! as [string, RequestInit]
  expect(url).toBe('/api/applications/application%2Fid/documents')
  expect(options.method).toBe('POST')
  expect(options.body).toBeInstanceOf(FormData)
  expect((options.body as FormData).get('document_type')).toBe('CV')
  expect((options.body as FormData).get('file')).toBe(file)
  expect(options.headers).toBeUndefined()
})

it('builds export and document download links with filters and encoded IDs', () => {
  expect(api.applicationExportUrl('csv')).toBe('/api/exports/applications.csv')
  expect(api.applicationExportUrl('xlsx', { company: 'North Star', status: 'INTERVIEW', source: '' })).toBe('/api/exports/applications.xlsx?company=North+Star&status=INTERVIEW')
  expect(api.documentContentUrl('application/id', 'document/id')).toBe('/api/applications/application%2Fid/documents/document%2Fid/content')
})
