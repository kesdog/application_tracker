import { request, type Application } from './api'
import { browserSession } from './auth'

export interface ImportRow { row: number; application: Record<string, unknown>; errors: string[]; duplicates: { id: string; company?: string }[] }
export interface ImportPreview { headers: string[]; fields: string[]; mapping: Record<string, string>; rows: ImportRow[] }
export interface MailReview { message_id: string; subject: string; reason: string; application_id: string | null; message_at: string | null; url: string }
export interface MergePreview { source: Application; target: Application; fields: string[]; counts: Record<string, number> }
export const previewMerge = (source: string, target: string) => request<MergePreview>(`/api/workspace/merge/preview?source_id=${encodeURIComponent(source)}&target_id=${encodeURIComponent(target)}`)
export const mergeApplications = (plan: MergePreview, fields: string[]) => request('/api/workspace/merge/' + encodeURIComponent(plan.target.id), {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_id: plan.source.id,
    source_revision: plan.source.revision, target_revision: plan.target.revision, take_source_fields: fields, confirmed: true }),
})
export const getTrash = (page = 1) => request<{ total: number; items: Application[] }>(`/api/workspace/trash?page=${page}`)
export const restoreApplication = (item: Application) => request('/api/workspace/trash/' + encodeURIComponent(item.id) + '/restore', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: item.revision }),
})
export const getMailReviews = (page = 1) => request<{ total: number; items: MailReview[] }>(`/api/workspace/mail-reviews?page=${page}`)
export const decideMailReview = (id: string, data: Record<string, unknown>) => request('/api/workspace/mail-reviews/' + encodeURIComponent(id), {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
})
export function previewImport(file: File, mapping?: Record<string, string>) {
  const body = new FormData(); body.set('file', file)
  if (mapping) body.set('mapping', JSON.stringify(mapping))
  return request<ImportPreview>('/api/workspace/imports/preview', { method: 'POST', body })
}
export function applyImport(file: File, mapping: Record<string, string>, selected: number[], duplicates: string) {
  const body = new FormData(); body.set('file', file); body.set('mapping', JSON.stringify(mapping))
  body.set('selected', JSON.stringify(selected)); body.set('duplicates', duplicates)
  return request<{ created: string[]; skipped: number }>('/api/workspace/imports/apply', { method: 'POST', body })
}
export function validateRecovery(file: File) {
  const body = new FormData(); body.set('file', file)
  return request<{ valid: boolean; applications: number; message: string }>('/api/workspace/recovery/validate', { method: 'POST', body })
}
export async function downloadBackup() {
  const response = await fetch('/api/workspace/backup', browserSession.withHeaders({ method: 'POST', cache: 'no-store' }))
  if (!response.ok) throw new Error('The backup could not be created. Check workspace storage and try again.')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a'); link.href = url; link.download = 'application-tracker-backup.zip'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
