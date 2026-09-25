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
}

export interface Application extends ApplicationCreate {
  id: string
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
  followup_delay_days: number | null
  max_followup_suggestions: number | null
}

export type NoteType = 'GENERAL' | 'ASSESSMENT' | 'EMAIL_DRAFT' | 'INTERVIEW' | 'AGENT'
export interface NoteInput { content: string; type: NoteType }
export interface Note extends NoteInput { id: string; application_id: string; created_by: string; created_at: string; updated_at: string }
export interface TaskInput { title: string; description: string | null; due_at: string | null }
export interface Task extends TaskInput { id: string; application_id: string; status: 'PENDING' | 'COMPLETED' | 'CANCELLED'; completed_at: string | null }
export interface FollowUpInput { due_at: string | null; template_reference: string | null }
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
  documents: Array<Record<string, string | null>>
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

export function listApplications(): Promise<Application[]> {
  return request('/api/applications')
}

export function getApplication(id: string): Promise<Application> {
  return request(`/api/applications/${encodeURIComponent(id)}`)
}

export function updateApplication(id: string, data: ApplicationUpdate): Promise<Application> {
  return request(`/api/applications/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
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
