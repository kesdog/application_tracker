export interface Health {
  status: 'ok'
  version: string
  database: 'connected'
}

export interface ApplicationCreate {
  job_title: string
  company: string
  date_applied: string
  job_url: string | null
  email_reference: string | null
  phone_number: string | null
  contact_type?: 'EMAIL' | 'PHONE'
  location?: string | null
  remote_policy?: string | null
  contract_type?: string | null
  source?: string | null
  description?: string | null
  requirements?: string | null
}

export interface Application extends ApplicationCreate {
  id: string
  contact_type: 'EMAIL' | 'PHONE'
  status: 'SUBMITTED' | 'INTERVIEW' | 'CLOSED'
  outcome: 'SUCCESSFUL' | 'UNSUCCESSFUL' | 'WITHDRAWN' | 'JOB_CANCELLED' | 'GHOSTED' | null
  location: string | null
  remote_policy: string | null
  contract_type: string | null
  source: string | null
  description: string | null
  requirements: string | null
  posting_status: 'UNKNOWN' | 'LIVE' | 'CLOSED'
  posting_last_checked_at: string | null
  posting_http_status: number | null
  posting_final_url: string | null
  posting_check_method: string | null
  posting_check_reason: string | null
  posting_check_failures: number
  followup_delay_days: number | null
  max_followup_suggestions: number | null
  deleted_at: string | null
  duplicate_warnings: DuplicateMatch[]
}
export interface DuplicateMatch { id: string; job_title: string; company: string; date_applied: string; reasons: string[] }
export interface ApplicationFilters {
  q?: string; status?: Application['status'] | ''; outcome?: NonNullable<Application['outcome']> | ''
  company?: string; title?: string; location?: string; contract_type?: string; source?: string
  remote_policy?: string; date_from?: string; date_to?: string; document_filename?: string
}

export type NoteType = 'GENERAL' | 'ASSESSMENT' | 'EMAIL_DRAFT' | 'INTERVIEW' | 'AGENT'
export interface NoteInput { content: string; type: NoteType }
export interface Note extends NoteInput { id: string; application_id: string; created_by: string; created_at: string; updated_at: string }
export interface TaskInput { title: string; description: string | null; due_at: string | null }
export interface Task extends TaskInput { id: string; application_id: string; status: 'PENDING' | 'COMPLETED' | 'CANCELLED'; completed_at: string | null }
export type FollowUpChannel = 'EMAIL' | 'PHONE' | 'BOTH'
export interface FollowUpInput { due_at: string | null; template_reference: string | null; channel: FollowUpChannel }
export interface FollowUp extends FollowUpInput { id: string; application_id: string; sequence_number: number; status: 'PENDING' | 'DRAFTED' | 'SENT' | 'CANCELLED'; sent_at: string | null }
export interface ApplicationWork { notes: Note[]; tasks: Task[]; followups: FollowUp[]; followup_delay_days: number; max_followup_suggestions: number }

export type InterviewType = 'PHONE' | 'HR' | 'TECHNICAL' | 'ONSITE' | 'FINAL' | 'OTHER'
export interface InterviewInput {
  type: InterviewType
  scheduled_at: string
  duration: number | null
  location: string | null
  meeting_url: string | null
  interviewer: string | null
  email_reference: string | null
  notes: string | null
  result: string | null
}
export interface Interview extends InterviewInput {
  id: string
  application_id: string
  created_at: string
  updated_at: string
}
export interface ApplicationSummary { id: string; job_title: string; company: string }
export interface InterviewListItem extends Interview { application: ApplicationSummary }
export interface TaskListItem extends Task { application: ApplicationSummary }
export interface InterviewContext {
  interview: Interview
  application: Application
  notes: Note[]
  tasks: Task[]
  documents: ApplicationDocument[]
}

export type ActorType = 'HUMAN' | 'AGENT' | 'SYSTEM'
export interface TimelineEvent {
  id: string
  application_id: string
  event_type: string
  actor_type: ActorType
  actor_reference: string | null
  summary: string
  metadata: Record<string, unknown>
  created_at: string
}
export interface TimelineEntryInput { summary: string; occurred_at: string }
export interface Timeline { events: TimelineEvent[]; undo_available: boolean }
export interface UndoResult { audit_id: string; entity_type: string; entity_id: string; fields: string[] }
export interface DashboardCounts { active_applications: number; followups_due: number; followups_overdue: number; tasks_due: number; tasks_overdue: number; upcoming_interviews: number }
export interface UpcomingItem { id: string; kind: 'TASK' | 'FOLLOWUP' | 'INTERVIEW'; title: string; due_at: string; status: string; application: ApplicationSummary }
export interface RecentActivity { id: string; event_type: string; summary: string; actor_type: ActorType; created_at: string; application: ApplicationSummary }
export interface DashboardData { counts: DashboardCounts; upcoming: UpcomingItem[]; due_followups: UpcomingItem[]; overdue_followups: UpcomingItem[]; recent_activity: RecentActivity[] }
export type DocumentType = 'CV' | 'COVER_LETTER'
export interface ApplicationDocument {
  id: string; application_id: string; type: DocumentType; filename: string
  storage_path: string | null; external_reference: string | null
  created_at: string; updated_at: string
}
export interface AgentPermissions { read: boolean; create: boolean; edit: boolean; draft: boolean; tasks: boolean; interviews: boolean }
export interface AgentSettings { configured: boolean; permissions: AgentPermissions }
export interface AgentTokenCreated extends AgentSettings { token: string }
export interface PostingCheckResult { status: Application['posting_status']; checked_at: string; http_status: number | null; final_url: string | null; method: string; reason: string; failures: number }
export interface AgentConnectionInfo { local_mcp_command: string; rest_endpoint: string; mcp_transport: 'stdio' | 'streamable-http'; remote_mcp_endpoint: string | null }
export interface IntegrationStatus { mail: { connected: boolean }; calendar: { connected: boolean } }
export interface DraftResult { location: 'LOCAL_NOTE' | 'MAILBOX'; note_id: string | null; message_reference: string | null; message: string }

export function getAgentSettings(): Promise<AgentSettings> { return request('/api/settings/agent') }
export function getAgentConnectionInfo(): Promise<AgentConnectionInfo> { return request('/api/settings/agent/connection') }
export function regenerateAgentToken(): Promise<AgentTokenCreated> { return request('/api/settings/agent/token', { method: 'POST' }) }
export function saveAgentPermissions(permissions: AgentPermissions): Promise<AgentSettings> {
  return request('/api/settings/agent/permissions', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(permissions) })
}
export function getIntegrationStatus(): Promise<IntegrationStatus> { return request('/api/integrations') }
export function draftEmailFollowup(applicationId: string, followupId: string, content: string): Promise<DraftResult> {
  return request(`/api/applications/${encodeURIComponent(applicationId)}/followups/${encodeURIComponent(followupId)}/draft`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }),
  })
}

export function getWork(id: string): Promise<ApplicationWork> {
  return request(`/api/applications/${encodeURIComponent(id)}/work`)
}

function writeChild<T>(applicationId: string, kind: string, data: unknown, itemId?: string): Promise<T> {
  return request(`/api/applications/${encodeURIComponent(applicationId)}/${kind}${itemId ? `/${encodeURIComponent(itemId)}` : ''}`, {
    method: itemId ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
}
export const createNote = (id: string, data: NoteInput) => writeChild<Note>(id, 'notes', data)
export const updateNote = (id: string, noteId: string, data: NoteInput) => writeChild<Note>(id, 'notes', data, noteId)
export const createTask = (id: string, data: TaskInput) => writeChild<Task>(id, 'tasks', data)
export const updateTask = (id: string, taskId: string, data: { status: Task['status'] }) => writeChild<Task>(id, 'tasks', data, taskId)
export const createFollowUp = (id: string, data: FollowUpInput) => writeChild<FollowUp>(id, 'followups', data)
export const updateFollowUp = (id: string, followupId: string, data: { status: FollowUp['status'] }) => writeChild<FollowUp>(id, 'followups', data, followupId)

export function listApplicationInterviews(applicationId: string): Promise<Interview[]> {
  return request(`/api/applications/${encodeURIComponent(applicationId)}/interviews`)
}

export function createInterview(applicationId: string, data: InterviewInput): Promise<Interview> {
  return writeChild<Interview>(applicationId, 'interviews', data)
}

export function updateInterview(applicationId: string, interviewId: string, data: Partial<InterviewInput>): Promise<Interview> {
  return writeChild<Interview>(applicationId, 'interviews', data, interviewId)
}

export function deleteInterview(applicationId: string, interviewId: string): Promise<void> {
  return request(`/api/applications/${encodeURIComponent(applicationId)}/interviews/${encodeURIComponent(interviewId)}`, { method: 'DELETE' })
}

export function listInterviews(): Promise<InterviewListItem[]> {
  return request('/api/interviews')
}

export function getInterviewContext(interviewId: string): Promise<InterviewContext> {
  return request(`/api/interviews/${encodeURIComponent(interviewId)}/context`)
}

export function listTasks(): Promise<TaskListItem[]> {
  return request('/api/tasks')
}

export type ApplicationUpdate = Partial<Omit<Application, 'id'>>

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, cache: 'no-store' })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      const detail = body?.detail
      const message = Array.isArray(detail)
        ? detail.map((error: { msg: string }) => error.msg).join('. ')
        : typeof detail === 'string' ? detail : `Request failed (${response.status})`
      throw new Error(message)
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } finally {
    clearTimeout(timeout)
  }
}

export function listApplications(filters: ApplicationFilters = {}): Promise<Application[]> {
  const params = filterParams(filters)
  const query = params.toString()
  return request(`/api/applications${query ? `?${query}` : ''}`)
}

function filterParams(filters: ApplicationFilters): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value)
  return params
}

export function applicationExportUrl(format: 'csv' | 'xlsx', filters: ApplicationFilters = {}): string {
  const query = filterParams(filters).toString()
  return `/api/exports/applications.${format}${query ? `?${query}` : ''}`
}

export function listDocuments(applicationId: string): Promise<ApplicationDocument[]> {
  return request(`/api/applications/${encodeURIComponent(applicationId)}/documents`)
}

export function createDocument(
  applicationId: string,
  data: { document_type: DocumentType; file?: File; filename?: string; external_reference?: string },
): Promise<ApplicationDocument> {
  const body = new FormData()
  body.set('document_type', data.document_type)
  if (data.file) body.set('file', data.file)
  if (data.filename) body.set('filename', data.filename)
  if (data.external_reference) body.set('external_reference', data.external_reference)
  return request(`/api/applications/${encodeURIComponent(applicationId)}/documents`, { method: 'POST', body })
}

export function documentContentUrl(applicationId: string, documentId: string): string {
  return `/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/content`
}

export function getDashboard(): Promise<DashboardData> { return request('/api/dashboard') }

export function getApplication(id: string): Promise<Application> {
  return request(`/api/applications/${encodeURIComponent(id)}`)
}

export function updateApplication(id: string, data: ApplicationUpdate): Promise<Application> {
  return request(`/api/applications/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
}

export function checkPosting(id: string): Promise<PostingCheckResult> {
  return request(`/api/applications/${encodeURIComponent(id)}/check-posting`, { method: 'POST' })
}

export function deleteApplication(id: string): Promise<void> {
  return request(`/api/applications/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function getTimeline(id: string): Promise<Timeline> {
  return request(`/api/applications/${encodeURIComponent(id)}/timeline`)
}

export function createTimelineEntry(id: string, data: TimelineEntryInput): Promise<TimelineEvent> {
  return request(`/api/applications/${encodeURIComponent(id)}/timeline`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
}

export function updateTimelineEntry(id: string, eventId: string, data: Partial<TimelineEntryInput>): Promise<TimelineEvent> {
  return request(`/api/applications/${encodeURIComponent(id)}/timeline/${encodeURIComponent(eventId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
}

export function undoLastChange(id: string): Promise<UndoResult> {
  return request(`/api/applications/${encodeURIComponent(id)}/undo`, { method: 'POST' })
}

export function createApplication(data: ApplicationCreate): Promise<Application> {
  return request('/api/applications', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function getHealth(): Promise<Health> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch('/api/health', { signal: controller.signal, cache: 'no-store' })
    if (!response.ok) throw new Error(`Health check failed (${response.status})`)
    const body: unknown = await response.json()
    if (typeof body !== 'object' || body === null ||
        !('status' in body) || body.status !== 'ok' ||
        !('version' in body) || typeof body.version !== 'string' || !body.version ||
        !('database' in body) || body.database !== 'connected') {
      throw new Error('Unexpected health response')
    }
    return body as Health
  } finally {
    clearTimeout(timeout)
  }
}
