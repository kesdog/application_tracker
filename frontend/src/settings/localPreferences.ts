export function readPreference(key: string): unknown {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') }
  catch { return null }
}
export function writePreference(key: string, value: unknown): boolean {
  try { localStorage.setItem(key, JSON.stringify(value)); return true }
  catch { return false }
}
