import { reactive } from 'vue'

interface InstallEvent extends Event { prompt(): Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }
export const phoneShell = reactive({ available: false, installed: false, message: '' })
let installEvent: InstallEvent | null = null

export function registerPhoneShell() {
  phoneShell.installed = window.matchMedia('(display-mode: standalone)').matches || !!(navigator as Navigator & { standalone?: boolean }).standalone
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); installEvent = event as InstallEvent; phoneShell.available = true
  })
  window.addEventListener('appinstalled', () => { phoneShell.installed = true; phoneShell.available = false; installEvent = null })
  if ('serviceWorker' in navigator && window.isSecureContext) {
    void navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { phoneShell.message = 'Phone installation is unavailable right now. You can continue using the browser.' })
  }
}

export async function installPhoneShell() {
  if (!installEvent) return
  const event = installEvent
  installEvent = null; phoneShell.available = false
  try {
    await event.prompt()
    const choice = await event.userChoice
    phoneShell.message = choice.outcome === 'accepted' ? 'Installation requested. Open Application Tracker from your home screen.' : 'You can install later from your browser menu.'
  } catch { phoneShell.message = 'Use your browser menu to install Application Tracker.' }
}
