import { afterEach, expect, it, vi } from 'vitest'
import { applicationExportUrl, createDocument, documentContentUrl, listDocuments } from './api'

afterEach(() => vi.unstubAllGlobals())

it('builds all and current-view export URLs', () => {
  expect(applicationExportUrl('csv')).toBe('/api/exports/applications.csv')
  expect(applicationExportUrl('xlsx', { company: 'North Star', status: 'INTERVIEW', source: '' }))
    .toBe('/api/exports/applications.xlsx?company=North+Star&status=INTERVIEW')
})

it('lists documents and builds an encoded download URL', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('[]'))
  vi.stubGlobal('fetch', fetchMock)
  await expect(listDocuments('application/id')).resolves.toEqual([])
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/application%2Fid/documents', expect.objectContaining({ cache: 'no-store' }))
  expect(documentContentUrl('application/id', 'document/id'))
    .toBe('/api/applications/application%2Fid/documents/document%2Fid/content')
})

it('uploads a document as multipart form data', async () => {
  const saved = { id: 'document-1', filename: 'cv.pdf' }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(saved), { status: 201 }))
  vi.stubGlobal('fetch', fetchMock)
  const file = new File(['cv'], 'cv.pdf', { type: 'application/pdf' })
  await expect(createDocument('application-1', { document_type: 'CV', file })).resolves.toEqual(saved)
  const options = fetchMock.mock.calls[0]![1] as RequestInit
  expect(options.method).toBe('POST')
  expect(options.body).toBeInstanceOf(FormData)
  expect((options.body as FormData).get('document_type')).toBe('CV')
  expect((options.body as FormData).get('file')).toBe(file)
  expect(options.headers).toBeUndefined()
})
