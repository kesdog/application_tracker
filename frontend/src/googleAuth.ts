import { disconnectGoogle, getConnections, startGoogle, type GoogleCapability } from './api'

/** Components own rendering/navigation; this client owns connection operations. */
export class GoogleLoginClient {
  async status() { return (await getConnections()).google }

  async authorizationUrl(capabilities: GoogleCapability[]) {
    const result = await startGoogle(capabilities)
    const url = new URL(result.authorization_url)
    if (url.origin !== 'https://accounts.google.com' || url.pathname !== '/o/oauth2/v2/auth') throw new Error('Invalid Google authorization address.')
    return url.href
  }

  disconnect() { return disconnectGoogle() }
}

export const googleLogin = new GoogleLoginClient()
