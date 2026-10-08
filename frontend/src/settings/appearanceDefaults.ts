export const legacyDefaultAppearance = {
  version: 1 as const,
  primary: '#263e5c', primaryHover: '#192d45', link: '#24568b', focus: '#527ba8',
  background: '#f5f6f8', surface: '#ffffff', surfaceMuted: '#edf1f5', border: '#dce2e9',
  text: '#202c3d', textMuted: '#576678',
  submitted: '#2a5189', interview: '#654388', successful: '#216344', unsuccessful: '#a12c32',
  withdrawn: '#66717f', cancelled: '#844d15', ghosted: '#6f7782',
  overdue: '#b33b42', dueSoon: '#b7791f', live: '#216344', postingClosed: '#66717f',
}

export const defaultAppearance = {
  ...legacyDefaultAppearance,
  primary: '#1c5b53', primaryHover: '#12463f', link: '#1b625b', focus: '#347f75',
  background: '#f7f6f2', surface: '#fffefb', surfaceMuted: '#eeeee7', border: '#b5bdb3',
  text: '#24352f', textMuted: '#526257', dueSoon: '#80501a',
  withdrawn: '#536171', ghosted: '#586473', postingClosed: '#536171',
}

export type AppearanceSettings = { [K in keyof typeof defaultAppearance]: K extends 'version' ? 1 : string }
export type AppearanceColor = Exclude<keyof AppearanceSettings, 'version'>
export const appearanceColors = Object.keys(defaultAppearance).filter(key => key !== 'version') as AppearanceColor[]
export const appearanceStorageKey = 'application-tracker:appearance'

export function normalizeHex(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const hex = value.trim()
  if (/^#[\da-f]{6}$/i.test(hex)) return hex.toLowerCase()
  if (/^#[\da-f]{3}$/i.test(hex)) return '#' + [...hex.slice(1)].map(c => c + c).join('').toLowerCase()
  return null
}

export function parseAppearance(value: unknown): AppearanceSettings {
  const result = { ...defaultAppearance }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result
  const stored = value as Record<string, unknown>
  if (stored.version !== undefined && stored.version !== 1) return result
  for (const key of appearanceColors) result[key] = normalizeHex(stored[key]) ?? result[key]
  return result
}
