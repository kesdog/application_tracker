// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { appearance, appearanceSaveError, applyAppearancePreset, loadAppearance, resetAppearance, setThemeMode, themeMode, themePalettesStorageKey, updateAppearance } from '../../src/settings/appearanceStore'
import { appearanceColors, appearanceStorageKey, defaultAppearance, parseAppearance } from '../../src/settings/appearanceDefaults'
import { appearancePresets } from '../../src/settings/appearancePresets'
import { contrastRatio, readableText } from '../../src/settings/colorContrast'
import { defaultTablePreferences, parseTablePreferences, resetTablePreferences, tablePreferences, tablePreferencesKey, updateTablePreferences } from '../../src/settings/tablePreferences'

beforeEach(() => { localStorage.clear(); loadAppearance(); resetTablePreferences() })
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); loadAppearance(); resetTablePreferences() })

it('merges valid saved colors and ignores malformed, unknown and future settings', () => {
  expect(parseAppearance({ primary: '#ABC', surface: 'red', injected: '#123456' })).toEqual({ ...defaultAppearance, primary: '#aabbcc' })
  for (const value of [null, [], 'bad', { version: 2, primary: '#abcdef' }]) expect(parseAppearance(value)).toEqual(defaultAppearance)
  localStorage.setItem(appearanceStorageKey, '{broken')
  expect(() => loadAppearance()).not.toThrow()
  expect(appearance).toEqual(defaultAppearance)
})

it('previews, persists, reloads and resets colors without storing invalid input', () => {
  expect(updateAppearance('interview', '#ABC')).toBe(true)
  expect(document.documentElement.style.getPropertyValue('--at-interview')).toBe('#aabbcc')
  expect(JSON.parse(localStorage.getItem(appearanceStorageKey)!)).toMatchObject({ version: 1, interview: '#aabbcc' })
  expect(updateAppearance('interview', '#invalid')).toBe(false)
  loadAppearance()
  expect(appearance.interview).toBe('#aabbcc')
  resetAppearance()
  expect(appearance).toEqual(defaultAppearance)
  expect(JSON.parse(localStorage.getItem(appearanceStorageKey)!)).toEqual(defaultAppearance)
})

it('keeps the preview usable and explains when storage is unavailable', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  expect(() => updateAppearance('text', '#123456')).not.toThrow()
  expect(appearance.text).toBe('#123456')
  expect(appearanceSaveError.value).toContain('could not save')
})

it.each(appearancePresets)('applies and persists the $label preset through the same schema', preset => {
  expect(applyAppearancePreset(preset.id)).toBe(true)
  loadAppearance()
  expect(appearance).toEqual(preset.colors)
  expect(contrastRatio(appearance.text, appearance.background)).toBeGreaterThanOrEqual(4.5)
  expect(contrastRatio(appearance.textMuted, appearance.surface)).toBeGreaterThanOrEqual(4.5)
  for (const key of appearanceColors) expect(contrastRatio(appearance[key], readableText(appearance[key]))).toBeGreaterThanOrEqual(4.5)
  updateAppearance('primary', '#123456')
  expect(preset.colors.primary).not.toBe('#123456')
})

it('rejects unknown presets and updates the native color scheme with dark settings', () => {
  expect(applyAppearancePreset('unknown')).toBe(false)
  expect(appearance).toEqual(defaultAppearance)
  applyAppearancePreset('dark')
  expect(document.documentElement.style.colorScheme).toBe('dark')
  resetAppearance()
  expect(document.documentElement.style.colorScheme).toBe('light')
})

it('switches themes without losing customized palettes and restores the active theme after reload', () => {
  updateAppearance('primary', '#123456')
  setThemeMode('dark')
  expect(themeMode.value).toBe('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  updateAppearance('link', '#aaffdd')
  loadAppearance()
  expect(themeMode.value).toBe('dark')
  setThemeMode('light')
  expect(appearance.primary).toBe('#123456')
  setThemeMode('dark')
  expect(appearance.link).toBe('#aaffdd')
})

it('ignores malformed palettes and rejects a light palette stored in the dark slot', () => {
  localStorage.setItem(themePalettesStorageKey, JSON.stringify({ version: 1, light: [], dark: defaultAppearance }))
  loadAppearance()
  setThemeMode('dark')
  expect(appearance).toEqual(appearancePresets.find(preset => preset.id === 'dark')!.colors)
})

it.each(appearancePresets.filter(preset => ['default', 'dark'].includes(preset.id)))('keeps all text roles readable on $label surfaces and tinted rows', preset => {
  const colors = preset.colors
  const blend = (foreground: string, background: string, amount: number) => '#' + [1, 3, 5].map(index => Math.round(parseInt(foreground.slice(index, index + 2), 16) * amount + parseInt(background.slice(index, index + 2), 16) * (1 - amount)).toString(16).padStart(2, '0')).join('')
  for (const background of [colors.background, colors.surface, colors.surfaceMuted, blend(colors.overdue, colors.surface, .1), blend(colors.dueSoon, colors.surface, .1), blend(colors.submitted, colors.surface, .1)]) {
    for (const text of [colors.text, colors.textMuted, colors.link]) expect(contrastRatio(text, background)).toBeGreaterThanOrEqual(4.5)
  }
  for (const role of ['submitted', 'interview', 'successful', 'unsuccessful', 'withdrawn', 'cancelled', 'ghosted', 'overdue', 'dueSoon', 'live', 'postingClosed'] as const) {
    expect(contrastRatio(colors[role], colors.surface)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(colors[role], blend(colors[role], colors.surface, .1))).toBeGreaterThanOrEqual(4.5)
  }
})

it('validates table preferences, preserves no optional columns and persists choices', () => {
  expect(parseTablePreferences({ version: 2 })).toEqual(defaultTablePreferences())
  expect(parseTablePreferences({ columns: [], pageSize: -1, density: 'invalid' })).toEqual({ ...defaultTablePreferences(), columns: [] })
  updateTablePreferences({ columns: ['source', 'source', 'outcome'], density: 'comfortable', pageSize: 50 })
  expect(parseTablePreferences(JSON.parse(localStorage.getItem(tablePreferencesKey)!))).toEqual(tablePreferences)
  expect(tablePreferences.columns).toEqual(['outcome', 'source'])
  resetTablePreferences()
  expect(tablePreferences).toEqual(defaultTablePreferences())
})
