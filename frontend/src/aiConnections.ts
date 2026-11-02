import { request } from './api'

export type AIProvider = 'chatgpt' | 'claude'
export interface AIConnections {
  chatgpt: { available: boolean; connected: boolean; can_use: boolean; account: string | null; email: string | null; accounts: { id: string; label: string; connected: boolean }[] }
  claude: { available: boolean; connected: boolean; method: 'api_key' }
}
const base = '/api/connections/ai'
const json = (method: string, body: unknown) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const getAIConnections = () => request<AIConnections>(base)
export const startChatGPT = (account: string | null) => request<{ authorization_url: string }>(base + '/chatgpt/start', json('POST', { account }))
export const connectClaude = (key: string) => request<AIConnections>(base + '/claude', json('PUT', { api_key: key }), 30000)
export const disconnectAI = (provider: AIProvider) => request<{ connections: AIConnections; message: string }>(`${base}/${provider}/disconnect`, { method: 'POST' }, 30000)
export const getAIModels = (provider: AIProvider) => request<{ id: string; name: string }[]>(`${base}/${provider}/models`, {}, 30000)
export const testAI = (provider: AIProvider, model: string) => request<{ message: string }>(`${base}/${provider}/test`, json('POST', { model }), 60000)
