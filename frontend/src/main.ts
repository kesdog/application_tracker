import { createApp } from 'vue'
import App from './App.vue'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import { trackerPreset } from './settings/primePreset'
import { loadAppearance } from './settings/appearanceStore'
import 'primeicons/primeicons.css'
import './styles/theme.css'

loadAppearance()
createApp(App)
  .use(PrimeVue, {
    license: import.meta.env.VITE_PRIMEUI_LICENSE_KEY || undefined,
    theme: { preset: trackerPreset, options: { darkModeSelector: '[data-theme="dark"]', cssLayer: { name: 'primevue', order: 'legacy, primevue, tracker' } } },
  })
  .use(ConfirmationService)
  .directive('tooltip', Tooltip)
  .mount('#app')
