import { GoogleAuthorization, loadGoogleOAuth, type Authorization } from './core/auth'
import { GoogleDriveTransport } from './core/drive'
import { PhoneSyncEngine } from './core/engine'
import type { ReplicaStore } from './core/storage'
export interface PhoneRuntime { auth: Authorization; engine: PhoneSyncEngine; preload(): Promise<unknown> }
export function createRuntime(store: ReplicaStore, clientId: string): PhoneRuntime {
  const auth = new GoogleAuthorization(clientId), transport = new GoogleDriveTransport(auth)
  return { auth, engine: new PhoneSyncEngine(store, transport), preload: loadGoogleOAuth }
}
