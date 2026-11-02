// @vitest-environment jsdom
import '../support/browser'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import PrimeVue from 'primevue/config'
import Navigation from '../../src/WorkspaceNavigation.vue'
import LanguageSettings from '../../src/components/settings/LanguageSettings.vue'
import TemplateField from '../../src/components/shared/TemplateField.vue'
import { errorText, loadLocale, locale, localeStorageKey, messageText, setLocale, t } from '../../src/i18n'
import { localizeValidation } from '../../src/i18n/validation'
import { applicationStatusMeta, statusOptions } from '../../src/presentation/applicationPresentation'
import catalog from '../../src/i18n/fr.json'
import * as api from '../../src/api'

vi.mock('../../src/api', async original => ({ ...await original<typeof import('../../src/api')>(), getGeneralSettings: vi.fn(), changeFollowUpLanguage: vi.fn() }))
beforeEach(() => { localStorage.clear(); setLocale('en'); vi.clearAllMocks() })
afterEach(() => { setLocale('en'); vi.restoreAllMocks() })

it('switches mounted navigation and metadata without changing canonical values', async () => {
  const wrapper = mount(Navigation, { props: { page: 'applications' } })
  expect(wrapper.text()).toContain('All applications')
  setLocale('fr'); await flushPromises()
  expect(wrapper.text()).toContain('Toutes les candidatures')
  expect(wrapper.get('a[href="#/settings"]').attributes('aria-label')).toBe('Paramètres')
  expect(document.documentElement.lang).toBe('fr')
  expect(applicationStatusMeta.SUBMITTED.label).toBe('Envoyée')
  expect(statusOptions[0]).toMatchObject({ value: 'SUBMITTED', label: 'Envoyée' })
  expect(JSON.parse(localStorage.getItem(localeStorageKey)!)).toBe('fr')
  loadLocale(); expect(locale.value).toBe('fr')
  setLocale('en'); await flushPromises()
  expect(wrapper.text()).toContain('All applications')
  wrapper.unmount()
})

it('falls back safely for invalid storage and applies a locale when storage is blocked', () => {
  localStorage.setItem(localeStorageKey, '"de"'); loadLocale(); expect(locale.value).toBe('en')
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  setLocale('fr'); expect(t('Settings')).toBe('Paramètres')
  setLocale('de'); expect(locale.value).toBe('fr')
})

it('localizes known, parameterized, network and unknown errors and native validation', () => {
  setLocale('fr')
  expect(errorText('Incorrect workspace password')).toBe("Mot de passe de l'espace incorrect")
  expect(messageText('Delete Engineer at Example? This action cannot be undone.')).toContain('Engineer chez Example')
  expect(errorText('Unexpected external provider response')).toBe('Impossible de terminer cette action. Réessayez.')
  expect(errorText('Failed to fetch')).toContain('connexion')
  const input = document.createElement('input'); input.required = true
  localizeValidation(input); expect(input.validationMessage).toBe('Veuillez renseigner ce champ.')
  input.value = 'Valid'; localizeValidation(input); expect(input.validationMessage).toBe('')
})

it('keeps authored messages unchanged while translating template hints and errors', () => {
  setLocale('fr')
  const wrapper = mount(TemplateField, { props: { modelValue: 'Hello Applications {company_name}', label: 'Follow-up message', variables: [] } })
  expect(wrapper.text()).toContain('Insérer une variable')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Hello Applications {company_name}')
  wrapper.unmount()
})

it('keeps interface and email languages independent and preserves versions on a bulk update', async () => {
  vi.mocked(api.getGeneralSettings).mockResolvedValue({ revision: 4, language: 'English' } as api.GeneralSettings)
  vi.mocked(api.changeFollowUpLanguage).mockResolvedValue({ settings: {} as api.GeneralSettings, rewritten: 2 })
  const wrapper = mount(LanguageSettings, { global: { plugins: [[PrimeVue, { unstyled: true }]] } })
  await flushPromises()
  await wrapper.get('#interface-language').setValue('fr')
  expect(locale.value).toBe('fr')
  expect(api.changeFollowUpLanguage).not.toHaveBeenCalled()
  expect((wrapper.get('#default-email-language').element as HTMLSelectElement).value).toBe('en')
  await wrapper.get('input[type=checkbox]').setValue(true)
  expect(wrapper.text()).toContain('versions dans les langues précédentes')
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(api.changeFollowUpLanguage).toHaveBeenCalledWith('en', true, 4)
  expect(wrapper.get('[role=status]').text()).toContain('2')
  vi.mocked(api.changeFollowUpLanguage).mockRejectedValue(new Error('Settings changed in another session. Reload before saving.'))
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('autre session')
  wrapper.unmount()
})

it('has a French translation for every literal message and preserves interpolation parameters', () => {
  const root = resolve('src')
  const files = readdirSync(root, { recursive: true }).filter((file): file is string => typeof file === 'string' && /\.(vue|ts)$/.test(file) && !file.startsWith('i18n'))
  const missing: string[] = []
  for (const file of files) {
    const source = readFileSync(resolve(root, file), 'utf8')
    for (const match of source.matchAll(/\bt\(((?:"(?:\\.|[^"\\])*")|(?:'(?:\\.|[^'\\])*'))/g)) {
      const parsed = ts.createSourceFile('key.ts', 'const key = ' + match[1], ts.ScriptTarget.Latest, true)
      const declaration = (parsed.statements[0] as ts.VariableStatement).declarationList.declarations[0]!
      const key = (declaration.initializer as ts.StringLiteral).text
      if (!Object.hasOwn(catalog, key)) missing.push(file + ': ' + key)
    }
  }
  expect(missing).toEqual([])
  const parameters = (text: string) => [...new Set(text.match(/\{p\d+\}/g) ?? [])].sort()
  for (const [key, value] of Object.entries(catalog)) expect(parameters(value), key).toEqual(parameters(key))
})
