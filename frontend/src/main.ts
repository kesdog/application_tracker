import { createApp, watchEffect } from 'vue'
import { loadLocale, locale } from './i18n'
import { installValidationLocale } from './i18n/validation'
import { frenchPrimeLocale } from './i18n/primeLocales'
import Root from './Root.vue'
import { registerPhoneShell } from './pwa'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import { trackerPreset } from './settings/primePreset'
import { loadAppearance } from './settings/appearanceStore'
import 'primeicons/primeicons.css'
import './styles/theme.css'

loadAppearance()
loadLocale()
installValidationLocale()
const app = createApp(Root)
  .use(PrimeVue, {
    license: import.meta.env.VITE_PRIMEUI_LICENSE_KEY || undefined,
    theme: { preset: trackerPreset, options: { darkModeSelector: '[data-theme="dark"]', cssLayer: { name: 'primevue', order: 'legacy, primevue, tracker' } } },
  })
  .use(ConfirmationService)
  .directive('tooltip', Tooltip)
const prime = app.config.globalProperties.$primevue
const englishPrimeLocale = JSON.parse(JSON.stringify(prime.config.locale))
watchEffect(() => { prime.config.locale = locale.value === 'fr' ? frenchPrimeLocale : englishPrimeLocale })
app.mount('#app')
registerPhoneShell()
