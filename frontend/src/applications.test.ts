import { afterEach, expect, it, vi } from 'vitest'
import { createApplication, getApplication, listApplications, updateApplication } from './api'

afterEach(() => vi.unstubAllGlobals())

it('posts the entered fields as JSON', async () => {
  const data = { job_title: 'Engineer', company: 'Example', date_applied: '2026-09-18', job_url: null, email_reference: 'Message 123' }
  const saved = { ...data, id: '123', status: 'SUBMITTED', outcome: null }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(saved), { status: 201 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(createApplication(data)).resolves.toEqual(saved)
  expect(fetchMock).toHaveBeenCalledWith('/api/applications', expect.objectContaining({ method: 'POST', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }))
})

it('lists persisted applications without a cached response', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('[]'))
  vi.stubGlobal('fetch', fetchMock)
  await expect(listApplications()).resolves.toEqual([])
  expect(fetchMock).toHaveBeenCalledWith('/api/applications', expect.objectContaining({ cache: 'no-store' }))
})

it('surfaces backend validation errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: 'Provide a job URL or an email reference' }] }), { status: 422 })))
  await expect(listApplications()).rejects.toThrow('Provide a job URL or an email reference')
})

it('handles a proxy failure that returns no JSON', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Unavailable', { status: 502 })))
  await expect(listApplications()).rejects.toThrow('Request failed (502)')
})

it('loads one application by ID', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"id":"123"}'))
  vi.stubGlobal('fetch', fetchMock)
  await expect(getApplication('123')).resolves.toEqual({ id: '123' })
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/123', expect.objectContaining({ cache: 'no-store' }))
})

it('sends partial updates and preserves an explicit null outcome', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"id":"123"}'))
  vi.stubGlobal('fetch', fetchMock)
  await updateApplication('123', { status: 'INTERVIEW', outcome: null })
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/123', expect.objectContaining({ method: 'PATCH', body: '{"status":"INTERVIEW","outcome":null}' }))
})

it('surfaces lifecycle validation messages from a patch', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"To reopen this application, explicitly clear its outcome"}', { status: 422 })))
  await expect(updateApplication('123', { status: 'INTERVIEW' })).rejects.toThrow('explicitly clear its outcome')
})
