import { afterEach, describe, expect, it, vi } from 'vitest'
import { getHealth } from './api'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('health connection', () => {
  it('reads a healthy backend response', async () => {
    const health = { status: 'ok', version: '0.1.0', database: 'connected' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(health))))
    await expect(getHealth()).resolves.toEqual(health)
  })

  it('rejects an unavailable backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(getHealth()).rejects.toThrow('Failed to fetch')
  })

  it('rejects an unhealthy database response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    await expect(getHealth()).rejects.toThrow('503')
  })

  it('rejects an unrelated or malformed response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"status":"ok"}')))
    await expect(getHealth()).rejects.toThrow('Unexpected health response')
  })

  it('times out a backend that never responds', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new Error('aborted')))
    })))
    const assertion = expect(getHealth()).rejects.toThrow('aborted')
    await vi.advanceTimersByTimeAsync(5000)
    await assertion
  })
})
