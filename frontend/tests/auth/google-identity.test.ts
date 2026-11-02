// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); delete window.google; document.querySelectorAll('script[src="https://accounts.google.com/gsi/client"]').forEach(script => script.remove()) })

it('loads the official SDK once for concurrent callers and retries after a content blocker failure', async () => {
  vi.resetModules()
  const { loadGoogleIdentity } = await import('../../src/googleIdentity')
  const first = loadGoogleIdentity()
  const failure = expect(first).rejects.toThrow('content blocker')
  expect(loadGoogleIdentity()).toBe(first)
  const script = document.querySelector<HTMLScriptElement>('script[src="https://accounts.google.com/gsi/client"]')!
  expect(script.async).toBe(true)
  script.dispatchEvent(new Event('error'))
  await failure
  const retry = loadGoogleIdentity()
  const sdk = { initialize: vi.fn(), renderButton: vi.fn() }
  window.google = { accounts: { id: sdk } }
  document.querySelector('script[src="https://accounts.google.com/gsi/client"]')!.dispatchEvent(new Event('load'))
  await expect(retry).resolves.toBe(sdk)
})

it('times out a stalled SDK request instead of leaving sign-in loading forever', async () => {
  vi.resetModules(); vi.useFakeTimers()
  const { loadGoogleIdentity } = await import('../../src/googleIdentity')
  const pending = expect(loadGoogleIdentity()).rejects.toThrow('could not load')
  await vi.advanceTimersByTimeAsync(12000)
  await pending
  expect(document.querySelector('script[src="https://accounts.google.com/gsi/client"]')).toBeNull()
})
