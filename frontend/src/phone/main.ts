import { createApp } from 'vue'
import PhoneApp from './PhoneApp.vue'
import { consumePairing, type PairingHandoff } from './core/pairing'
let handoff: PairingHandoff | undefined, pairingError = ''
try { handoff = consumePairing(window.location, window.history) }
catch (error) { pairingError = error instanceof Error ? error.message : 'Invalid pairing code' }
createApp(PhoneApp, { takeHandoff: () => { const value = handoff; handoff = undefined; return value }, pairingError }).mount('#phone-app')
