import { browserSession } from './auth'

export interface PhoneDevice { id: string; label: string; active: boolean; reason: string | null; created_at: string; latest: null | { state: string; attempts: number; error: string | null; accepted_at: string | null } }
export interface PhoneNotificationStatus { configured: boolean; public_key: string | null; devices: PhoneDevice[] }
export const getPhoneNotificationStatus = () => request<PhoneNotificationStatus>('/api/settings/notifications')
export const registerPhoneDevice = (subscription: PushSubscriptionJSON, label: string) => request<PhoneDevice>('/api/settings/notifications/devices', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...subscription, label }) })
export const removePhoneDevice = (id: string) => request<void>('/api/settings/notifications/devices/' + encodeURIComponent(id), { method: 'DELETE' })
export const testPhoneDevice = (id: string) => request<{ message: string }>('/api/settings/notifications/devices/' + encodeURIComponent(id) + '/test', { method: 'POST' })

export interface Health {
  status: 'ok'
  version: string
  database: 'connected'
}

export interface ApplicationCreate {
  job_title: string
  company: string
  intermediary?: string | null
  date_applied: string
  job_url: string | null
  email_reference: string | null
  phone_number: string | null
  contact_email?: string | null
  contact_name?: string | null
  deadline?: string | null
  deadline_kind?: 'APPLICATION_CLOSING' | 'FIRST_ROUND' | null
  contact_type?: 'EMAIL' | 'PHONE'
  location?: string | null
  remote_policy?: string | null
  contract_type?: string | null
  source?: string | null
  description?: string | null
  requirements?: string | null
  followup_delay_days?: number | null
  recipient_page_limit?: number | null
  max_followup_suggestions?: number | null
  followup_instructions?: string
  followup_customization?: Customization
  followup_paused?: boolean
}

export interface Application extends ApplicationCreate {
  revision: number
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
export interface NoteInput { content: string; type: NoteType; employer_reply?: boolean }
export interface Note extends NoteInput { id: string; application_id: string; created_by: string; created_at: string; updated_at: string }
export interface TaskInput { title: string; description: string | null; due_at: string | null }
export interface Task extends TaskInput { id: string; application_id: string; status: 'PENDING' | 'COMPLETED' | 'CANCELLED'; completed_at: string | null }
export type FollowUpChannel = 'EMAIL' | 'PHONE' | 'BOTH'
export interface FollowUpInput { due_at: string | null; template_reference: string | null; channel: FollowUpChannel }
export interface Customization { language?: string | null; tone?: string | null; signature?: string | null }
export interface FollowUp extends FollowUpInput {
  id: string; application_id: string; sequence_number: number; status: 'PREPARED' | 'READY' | 'SENT'; is_automatic: boolean; sent_at: string | null
  subject: string; body: string; instructions: string; customization: Customization; revision: number; approved_revision: number | null
  template_snapshot: Record<string, unknown>; variable_snapshot: Record<string, string>; prepared_at: string | null; updated_at: string
  snoozed_until: string | null; archived_at: string | null
  recipient_email?: string | null; recipient_name?: string | null; recipient_source_url?: string | null
}
export interface FollowUpChanges { recipient_email?: string | null; recipient_name?: string | null; recipient_source_url?: string | null; subject?: string; body?: string; instructions?: string; customization?: Customization; expected_revision?: number; status?: FollowUp['status']; sent_at?: string | null; due_at?: string; snoozed_until?: string | null; archived?: boolean }
export interface TemplateVariable { key: string; label: string; group: string; aliases: string[] }
export interface GeneralSettings {
  subject_template: string; body_template: string; signature: string; language: string; tone: string; instructions: string
  followup_delay_days: number; max_followup_suggestions: number; timezone: string; reminder_time: string
  notifications_enabled: boolean; quiet_start: string; quiet_end: string; daily_digest: boolean; revision: number
  unsuccessful_review_after: number
  recipient_page_limit: number
}
export interface RenderedTemplate { text: string; missing: string[]; unknown: string[] }
export interface TemplatePreview { subject: RenderedTemplate; body: RenderedTemplate; variables: Record<string, string> }
export interface MessageProposal { subject: RenderedTemplate; body: RenderedTemplate; expected_revision: number }
export interface FollowUpRow extends FollowUp { application: Application }
export interface FollowUpPage { items: FollowUpRow[]; total: number; page: number; page_size: number }
export interface OutcomeReview { threshold: number; unanswered_sent_count: number; last_reply_at: string | null; needs_review: boolean }
export interface OutcomeReviewPage { items: (OutcomeReview & { application: ApplicationSummary })[]; total: number; page: number; page_size: number }
export interface FollowUpAIResult { operation_id: string; expected_revision: number; status: 'revised_message' | 'mailbox_draft_created' | 'skipped' | 'needs_clarification' | 'failure'; agent_name: string; details: string; draft_reference: string | null; accepted_revision: number; recorded_at: string; reported_by: string }
export interface ApplicationWork { notes: Note[]; tasks: Task[]; followups: FollowUp[]; followup_delay_days: number; max_followup_suggestions: number; outcome_review?: OutcomeReview }

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
export interface PostingReviewPlan { application_id: string; job_url: string | null; searches: { label: string; url: string }[]; search_query: string; agent_search_prompt: string; instructions: string }
export interface PostingReviewInput { status: Application['posting_status']; evidence_url: string; notes: string; checked_at: string; same_position: boolean; replace_job_url: boolean }
export interface AgentConnectionInfo { local_mcp_command: string; rest_endpoint: string; mcp_transport: 'stdio' | 'streamable-http'; remote_mcp_endpoint: string | null }
export interface IntegrationStatus { mail: { connected: boolean }; calendar: { connected: boolean }; google?: GoogleConnection }
export type GoogleCapability = 'drive' | 'gmail_read' | 'gmail_drafts'
export interface GoogleConnection { configured: boolean; status: string; email: string | null; capabilities: Record<GoogleCapability, boolean>; updated_at: string | null; verified_at: string | null; message: string | null }
export function getConnections(): Promise<{ google: GoogleConnection }> { return request('/api/connections') }
export function startGoogle(capabilities: GoogleCapability[]): Promise<{ authorization_url: string; expires_in: number }> {
  return request('/api/connections/google/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ capabilities }) })
}
export function disconnectGoogle(): Promise<GoogleConnection> { return request('/api/connections/google/disconnect', { method: 'POST' }) }
export function testGoogleDrive(recovery_key: string): Promise<{ verified: boolean; deleted: boolean; message: string }> {
  return request('/api/connections/google/drive-test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ recovery_key }) })
}
export interface DraftResult { location: 'LOCAL_NOTE' | 'MAILBOX'; note_id: string | null; message_reference: string | null; message: string }

export function getAgentSettings(): Promise<AgentSettings> { return request('/api/settings/agent') }
export function getAgentConnectionInfo(): Promise<AgentConnectionInfo> { return request('/api/settings/agent/connection') }
export function regenerateAgentToken(): Promise<AgentTokenCreated> { return request('/api/settings/agent/token', { method: 'POST' }) }
export function saveAgentPermissions(permissions: AgentPermissions): Promise<AgentSettings> {
  return request('/api/settings/agent/permissions', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(permissions) })
}
export function getIntegrationStatus(): Promise<IntegrationStatus> { return request('/api/integrations') }
export function draftEmailFollowup(applicationId: string, followupId: string, content: string, expected_revision?: number, operation_id: string = crypto.randomUUID()): Promise<DraftResult> {
  return request(`/api/applications/${encodeURIComponent(applicationId)}/followups/${encodeURIComponent(followupId)}/draft`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, expected_revision, operation_id }),
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
export const updateFollowUp = (id: string, followupId: string, data: FollowUpChanges) => writeChild<FollowUp>(id, 'followups', data, followupId)
export const getGeneralSettings = (): Promise<GeneralSettings> => request('/api/settings/general')
export function saveGeneralSettings(data: GeneralSettings): Promise<GeneralSettings> {
  const { revision, ...values } = data
  return request('/api/settings/general', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...values, expected_revision: revision }) })
}
export const getTemplateVariables = (): Promise<TemplateVariable[]> => request('/api/followups/variables')
export const getFollowUpAgentStatus = (): Promise<{ active: boolean; can_draft: boolean }> => request('/api/followups/agent-status')
export const getRenderedFollowUp = (id: string, followupId: string): Promise<TemplatePreview & { revision: number }> => request(`/api/applications/${encodeURIComponent(id)}/followups/${encodeURIComponent(followupId)}/rendered-message`)
export const queueFollowUpDraft = (id: string, followupId: string, revision: number): Promise<Task> => request(`/api/applications/${encodeURIComponent(id)}/followups/${encodeURIComponent(followupId)}/draft-task`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision }) })
export const previewTemplate = (data: { subject: string; body: string; application_id?: string; customization?: Customization }): Promise<TemplatePreview> => request('/api/followups/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const getFollowUps = (query = ''): Promise<FollowUpPage> => request('/api/followups' + query)
export interface FollowUpNotice { id: string; followup: FollowUp; application: Pick<Application, 'id' | 'company' | 'job_title'> }
export const getFollowUpNotices = (): Promise<FollowUpNotice[]> => request('/api/followups/notices')
export const readFollowUpNotice = (id: string): Promise<{ read: boolean }> => request(`/api/followups/notices/${encodeURIComponent(id)}/read`, { method: 'POST' })
export const proposeFollowUp = (appId: string, id: string, latest: boolean): Promise<MessageProposal> => request(`/api/applications/${encodeURIComponent(appId)}/followups/${encodeURIComponent(id)}/proposal?latest=${latest}`)
export const applyFollowUpTemplate = (appId: string, id: string, expected_revision: number, latest: boolean): Promise<FollowUp> => request(`/api/applications/${encodeURIComponent(appId)}/followups/${encodeURIComponent(id)}/apply-template`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision, latest }) })
export const getFollowUpAIRequest = (appId: string, id: string): Promise<Record<string, unknown>> => request(`/api/applications/${encodeURIComponent(appId)}/followups/${encodeURIComponent(id)}/ai-request`)
export const getOutcomeReviews = (page = 1): Promise<OutcomeReviewPage> => request(`/api/followups/reviews?page=${page}&page_size=20`)
export interface RecipientJob { id: string; state: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'NO_RESULTS' | 'FAILED' | 'CANCELLED'; attempts: number; error: string | null; warnings: string[]; page_limit?: number; refresh_pages?: boolean; page_counts?: { fetched_pages?: number; reused_pages?: number } }
export interface RecipientCandidate { id: string; name: string | null; email: string | null; kind: 'recruiter_hr' | 'technical_lead' | 'general_contact'; role: string | null; source_url: string; evidence: string; company_match: string; vacancy_match: string; email_status: string; stale: boolean; context_current: boolean; excluded?: boolean;
  contact_priority?: { category: string; score: number; recommended_action: string; outreach_eligible: boolean };
  profile_urls?: { url: string; label: string }[];
  emails?: { email: string; purpose: string; exclusion_reason?: string | null }[];
  deliverability?: string; personal_ownership?: string; requires_review?: boolean;
  source_region?: string; source_sector?: string;
  fit?: { region?: { state: string; requested?: string | null; observed?: string | null }; sector?: { state: string; requested?: string | null; observed?: string | null } };
}
export interface RecipientFollowUp { id: string; sequence_number: number; revision: number; recipient_email: string | null; recipient_name: string | null }
export interface RecipientState { application_revision?: number; job: RecipientJob | null; candidates: RecipientCandidate[]; missing_followups: number; followups: RecipientFollowUp[]; page_limit?: number; page_limit_override?: number | null; default_page_limit?: number }
export interface RecipientQueue { queued: number; running: number; failed: number; missing_followups: number; concurrency_limit: number; available: boolean }
export const getRecipientState = (id: string): Promise<RecipientState> => request(`/api/applications/${encodeURIComponent(id)}/recipients`)
export const fetchRecipients = (id: string, refreshPages = false): Promise<RecipientJob> => request(`/api/applications/${encodeURIComponent(id)}/recipients/fetch`, { method: 'POST', ...(refreshPages ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_pages: true }) } : {}) })
export interface RecipientPageSummary { id: string; url: string; resolved_url: string | null; title: string; outcome: string; fetched_at: string | null; stale: boolean; candidate_count: number }
export interface RecipientPageDetail extends RecipientPageSummary { report: { summary: string; candidates: Array<{ name?: string | null; email?: string | null; role?: string | null; purpose?: string; exclusion_reason?: string | null }>; contact_links: string[]; error?: string; rendering_signals?: string[] } }
export interface RecipientPageList { items: RecipientPageSummary[]; total: number; page: number; page_size: number }
export const getRecipientPages = (applicationId?: string, page = 1): Promise<RecipientPageList> => request('/api/recipients/pages?' + new URLSearchParams({ ...(applicationId ? { application_id: applicationId } : {}), page: String(page), page_size: '10' }))
export const getRecipientPage = (id: string, applicationId?: string): Promise<RecipientPageDetail> => request('/api/recipients/pages/' + encodeURIComponent(id) + (applicationId ? '?' + new URLSearchParams({ application_id: applicationId }) : ''))
export const getRecipientQueue = (): Promise<RecipientQueue> => request('/api/recipients/queue')
export const fetchMissingRecipients = (): Promise<{ queued: number; applications: number; concurrency_limit: number }> => request('/api/recipients/queue-missing', { method: 'POST' })
export const chooseRecipient = (appId: string, followupId: string, candidateId: string, revision: number): Promise<FollowUp> => request(`/api/applications/${encodeURIComponent(appId)}/followups/${encodeURIComponent(followupId)}/recipient`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: candidateId, expected_revision: revision }) })
export const getFollowUpAIResults = (appId: string, id: string): Promise<FollowUpAIResult[]> => request(`/api/applications/${encodeURIComponent(appId)}/followups/${encodeURIComponent(id)}/ai-results`)
export const importFollowUpAIResult = (appId: string, id: string, result: Record<string, unknown>): Promise<FollowUpAIResult> => request(`/api/applications/${encodeURIComponent(appId)}/followups/${encodeURIComponent(id)}/ai-results`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result) })

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

export type ApplicationUpdate = Partial<Omit<Application, 'id' | 'revision'>> & { expected_revision?: number }

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(path, { ...browserSession.withHeaders(options), signal: controller.signal, cache: 'no-store' })
    if (!response.ok) {
      if (response.status === 401) browserSession.expire()
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

export function getPostingReview(id: string): Promise<PostingReviewPlan> {
  return request(`/api/applications/${encodeURIComponent(id)}/posting-review`)
}

export function recordPostingReview(id: string, review: PostingReviewInput): Promise<PostingCheckResult> {
  return request(`/api/applications/${encodeURIComponent(id)}/posting-review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(review) })
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

export function validateContact(data: { contact_email: string | null; phone_number: string | null }): Promise<{ contact_email: string | null; phone_number: string | null }> {
  return request('/api/contact-validation', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
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
