import { afterEach, expect, it, vi } from 'vitest'
import { createFollowUp, createNote, createTask, getWork, updateFollowUp, updateNote, updateTask } from './api'

afterEach(() => vi.unstubAllGlobals())

it('loads all work for the selected application', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"notes":[],"tasks":[],"followups":[]}'))
  vi.stubGlobal('fetch', fetchMock)
  await getWork('application-1')
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/application-1/work', expect.objectContaining({ cache: 'no-store' }))
})

it('creates and edits notes without forging authorship', async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
  vi.stubGlobal('fetch', fetchMock)
  await createNote('app', { content: 'Assessment', type: 'ASSESSMENT' })
  await updateNote('app', 'note', { content: 'Updated', type: 'GENERAL' })
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/applications/app/notes', expect.objectContaining({ method: 'POST', body: '{"content":"Assessment","type":"ASSESSMENT"}' }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/applications/app/notes/note', expect.objectContaining({ method: 'PATCH', body: '{"content":"Updated","type":"GENERAL"}' }))
})

it('sends UTC task due dates and lets the server set completion time', async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
  vi.stubGlobal('fetch', fetchMock)
  await createTask('app', { title: 'Prepare', description: null, due_at: '2026-09-25T12:00:00Z' })
  await updateTask('app', 'task', { status: 'COMPLETED' })
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/applications/app/tasks', expect.objectContaining({ method: 'POST', body: '{"title":"Prepare","description":null,"due_at":"2026-09-25T12:00:00Z"}' }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/applications/app/tasks/task', expect.objectContaining({ method: 'PATCH', body: '{"status":"COMPLETED"}' }))
})

it('requests follow-up defaults and records sent status without a send endpoint', async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
  vi.stubGlobal('fetch', fetchMock)
  await createFollowUp('app', { due_at: null, template_reference: null })
  await updateFollowUp('app', 'followup', { status: 'SENT' })
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/applications/app/followups', expect.objectContaining({ method: 'POST', body: '{"due_at":null,"template_reference":null}' }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/applications/app/followups/followup', expect.objectContaining({ method: 'PATCH', body: '{"status":"SENT"}' }))
})
