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
}

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
    return await response.json() as T
  } finally {
    clearTimeout(timeout)
  }
}

export function listApplications(): Promise<Application[]> {
  return request('/api/applications')
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
