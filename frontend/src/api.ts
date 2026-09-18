export interface Health {
  status: 'ok'
  version: string
  database: 'connected'
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
