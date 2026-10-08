import { appearanceColors, type AppearanceSettings } from './appearanceDefaults'
import { luminance, readableText } from './colorContrast'

export function appearanceVariable(key: string): string {
  return `--at-${key.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase())}`
}
export function applyAppearance(settings: AppearanceSettings): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  for (const key of appearanceColors) {
    root.style.setProperty(appearanceVariable(key), settings[key])
    root.style.setProperty(`${appearanceVariable(key)}-contrast`, readableText(settings[key]))
  }
  const mode = luminance(settings.background) < 0.179 ? 'dark' : 'light'
  root.style.colorScheme = mode
  root.dataset.theme = mode
  root.style.setProperty('--at-nav-background', mode === 'dark' ? settings.background : settings.primary)
  root.style.setProperty('--at-nav-text', mode === 'dark' ? settings.text : readableText(settings.primary))
  root.style.setProperty('--at-nav-accent', mode === 'dark' ? settings.primary : readableText(settings.primary))
}
