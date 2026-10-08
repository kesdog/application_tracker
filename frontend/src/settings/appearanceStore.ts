import { computed, reactive, readonly, ref } from 'vue'
import { appearanceColors, appearanceStorageKey, defaultAppearance, legacyDefaultAppearance, normalizeHex, parseAppearance, type AppearanceColor, type AppearanceSettings } from './appearanceDefaults'
import { applyAppearance } from './applyAppearance'
import { readPreference, writePreference } from './localPreferences'
import { appearancePresets } from './appearancePresets'
import { luminance } from './colorContrast'

const state = reactive({ ...defaultAppearance })
export const appearance = readonly(state)
export const appearanceSaveError = ref('')
export type ThemeMode = 'light' | 'dark'
export const themePalettesStorageKey = 'application-tracker:theme-palettes'
export const themeMode = computed<ThemeMode>(() => luminance(state.background) < 0.179 ? 'dark' : 'light')
const defaultDark = () => ({ ...appearancePresets.find(preset => preset.id === 'dark')!.colors })
let palettes: Record<ThemeMode, AppearanceSettings> = { light: { ...defaultAppearance }, dark: defaultDark() }

export function loadAppearance(): void {
  const stored = readPreference(themePalettesStorageKey) as { version?: number; light?: unknown; dark?: unknown } | null
  palettes = { light: { ...defaultAppearance }, dark: defaultDark() }
  if (stored?.version === 1) {
    const light = parseAppearance(stored.light)
    const dark = parseAppearance(stored.dark)
    if (luminance(light.background) >= 0.179) palettes.light = light
    if (luminance(dark.background) < 0.179) palettes.dark = dark
  }
  const current = parseAppearance(readPreference(appearanceStorageKey))
  // Upgrade the unchanged prototype palette; preserve user-customized colors.
  Object.assign(state, appearanceColors.every(key => current[key] === legacyDefaultAppearance[key]) ? defaultAppearance : current)
  palettes[themeMode.value] = { ...state }
  appearanceSaveError.value = ''
  applyAppearance(state)
}
export function saveAppearance(): void {
  palettes[themeMode.value] = { ...state }
  const currentSaved = writePreference(appearanceStorageKey, state)
  const palettesSaved = writePreference(themePalettesStorageKey, { version: 1, ...palettes })
  appearanceSaveError.value = currentSaved && palettesSaved ? '' : 'Appearance is applied for this session. Your browser could not save it for the next visit.'
}
export function setThemeMode(mode: ThemeMode): void {
  if (mode === themeMode.value) return
  palettes[themeMode.value] = { ...state }
  Object.assign(state, palettes[mode])
  applyAppearance(state)
  saveAppearance()
}
export function updateAppearance(key: AppearanceColor, value: string): boolean {
  const color = normalizeHex(value)
  if (!color) return false
  state[key] = color
  applyAppearance(state)
  saveAppearance()
  return true
}
export function resetAppearance(): void {
  Object.assign(state, defaultAppearance)
  applyAppearance(state)
  saveAppearance()
}

export function applyAppearancePreset(id: string): boolean {
  const preset = appearancePresets.find(item => item.id === id)
  if (!preset) return false
  Object.assign(state, preset.colors)
  applyAppearance(state)
  saveAppearance()
  return true
}
