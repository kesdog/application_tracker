<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import PageTabs from './components/shared/PageTabs.vue'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import { onMounted, onUnmounted, ref } from 'vue'
import AppearanceSettings from './components/settings/AppearanceSettings.vue'
import LanguageSettings from './components/settings/LanguageSettings.vue'
import GoogleSettings from './components/settings/GoogleSettings.vue'
import MailSyncSettings from './components/settings/MailSyncSettings.vue'
import AIConnections from './components/settings/AIConnections.vue'
import WorkspaceData from './components/settings/WorkspaceData.vue'
import FollowUpSettings from './components/settings/FollowUpSettings.vue'
import PhoneInstallation from './components/settings/PhoneInstallation.vue'
import PhoneNotifications from './components/settings/PhoneNotifications.vue'
import PhoneSetup from './components/sync/PhoneSetup.vue'
import { getAgentConnectionInfo, getAgentSettings, getHealth, getIntegrationStatus, regenerateAgentToken, saveAgentPermissions, type AgentConnectionInfo, type AgentPermissions, type AgentSettings, type Health, type IntegrationStatus } from './api'

const settingsTab = ref('appearance')
const selectedProvider = ref('')
function readCategory() {
  const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const requested = query.get('tab')
  const provider = query.get('provider')
  selectedProvider.value = provider === 'chatgpt' || provider === 'claude' ? provider : ''
  if (requested && ['appearance', 'followups', 'connections', 'phone', 'data', 'agent'].includes(requested)) settingsTab.value = requested
}
readCategory()
const settings = ref<AgentSettings | null>(null)
const integrations = ref<IntegrationStatus | null>(null)
const connectionInfo = ref<AgentConnectionInfo | null>(null)
const health = ref<Health | null>(null)
const connection = ref<'checking' | 'connected' | 'disconnected'>('checking')
const token = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const message = ref('')
const permissions = ref<AgentPermissions>({ read: true, create: false, edit: false, draft: false, tasks: false, interviews: false })
const labels: { key: keyof AgentPermissions; label: string; help: string }[] = [
  { key: 'read', get label() { return t("Read") }, get help() { return t("View applications, activity, and upcoming work.") } },
  { key: 'create', get label() { return t("Create") }, get help() { return t("Create applications.") } },
  { key: 'edit', get label() { return t("Edit") }, get help() { return t("Change application details and status.") } },
  { key: 'draft', get label() { return t("Draft") }, get help() { return t("Create notes and follow-ups, and record a follow-up as sent.") } },
  { key: 'tasks', get label() { return t("Tasks") }, get help() { return t("Create and complete tasks.") } },
  { key: 'interviews', get label() { return t("Interviews") }, get help() { return t("Schedule and update interviews.") } },
]

async function load() {
  loading.value = true; error.value = ''
  try { settings.value = await getAgentSettings(); permissions.value = { ...settings.value.permissions }; integrations.value = await getIntegrationStatus(); connectionInfo.value = await getAgentConnectionInfo() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to load agent settings.") }
  finally { loading.value = false }
}

async function checkConnection() {
  connection.value = 'checking'
  health.value = null
  try { health.value = await getHealth(); connection.value = 'connected' }
  catch { connection.value = 'disconnected' }
}

async function generate() {
  saving.value = true; error.value = ''; message.value = ''; token.value = ''
  try {
    const result = await regenerateAgentToken()
    settings.value = result; permissions.value = { ...result.permissions }; token.value = result.token
    message.value = t("Copy this token now. It will disappear when you leave this page.")
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to generate token.") }
  finally { saving.value = false }
}

async function save() {
  saving.value = true; error.value = ''; message.value = ''
  try { settings.value = await saveAgentPermissions(permissions.value); message.value = t("Permissions saved.") }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to save permissions.") }
  finally { saving.value = false }
}

onMounted(() => { void load(); void checkConnection(); window.addEventListener('hashchange', readCategory) })
onUnmounted(() => window.removeEventListener('hashchange', readCategory))
</script>

<template>
  <section aria-labelledby="agent-settings-title">
    <h2 id="agent-settings-title">{{ t("Settings") }}</h2>
    <p class="intro">{{ t("Choose a category to adjust your workspace.") }}</p>
    <PageTabs v-model="settingsTab" :label="t('Settings categories')" :tabs="[
      { value: 'appearance', get label() { return t('Appearance') }, icon: 'pi-palette' },
      { value: 'followups', get label() { return t('Follow-ups') }, icon: 'pi-envelope' },
      { value: 'connections', get label() { return t('Connections') }, icon: 'pi-sync' },
      { value: 'phone', get label() { return t('Phone') }, icon: 'pi-mobile' },
      { value: 'data', get label() { return t('Data & recovery') }, icon: 'pi-database' },
      { value: 'agent', get label() { return t('Agent & system') }, icon: 'pi-microchip-ai' },
    ]">
      <template #appearance><LanguageSettings /><AppearanceSettings /></template>
      <template #followups><FollowUpSettings /></template>
      <template #phone><PhoneSetup /><details class="panel"><summary>{{ t("Phone reminders") }}</summary><PhoneNotifications /></details><details class="panel"><summary>{{ t("Install on your phone") }}</summary><PhoneInstallation /></details></template>
      <template #data><WorkspaceData /></template>
      <template #agent>
    <p class="hint">{{ t("Create a token for an external agent, then choose what it can do. Agents cannot delete applications.") }}</p>
    <p v-if="loading" role="status">{{ t("Loading agent settings…") }}</p><p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <template v-if="settings">
      <section class="panel"><h3>{{ t("Access token") }}</h3><p>{{ settings.configured ? t("An agent token is configured.") : t("No agent token has been created.") }}</p>
        <Button type="button" class="primary" :disabled="saving" @click="generate">{{ settings.configured ? t("Regenerate token") : t("Generate token") }}</Button>
        <p v-if="settings.configured" class="hint" role="note">{{ t("Regenerating immediately disconnects every client using this token, including ChatGPT and Claude. Reconfigure both clients with the new token.") }}</p>
        <div v-if="token" class="token-box"><label for="agent-token">{{ t("New token — shown once") }}</label><Textarea class="at-form-control" id="agent-token" :value="token" readonly rows="3" @focus="($event.target as HTMLTextAreaElement).select()"></Textarea><p>{{ t("Copy it into your agent's secure configuration. This page does not store the plaintext token.") }}</p></div>
      </section>
      <details class="panel"><summary>{{ t("Agent permissions") }}</summary><form @submit.prevent="save"><p class="hint">{{ t("Changes apply to REST and MCP calls immediately.") }}</p>
        <label v-for="item in labels" :key="item.key" class="permission"><input v-model="permissions[item.key]" type="checkbox" :disabled="saving || !settings.configured" /><span><strong>{{ messageText(String((item.label) ?? '')) }}</strong><small>{{ messageText(String((item.help) ?? '')) }}</small></span></label>
        <Button class="primary" type="submit" :disabled="saving || !settings.configured">{{ t("Save permissions") }}</Button>
      </form></details>
    </template>
    <details class="panel" :open="Boolean(selectedProvider)"><summary>{{ t("Agent connection help") }}</summary>
      <dl class="connection-list"><div><dt>{{ t("Local MCP / stdio") }}</dt><dd><code>{{ connectionInfo?.local_mcp_command ?? 'Unavailable' }}</code></dd></div><div><dt>{{ t("Agent REST API") }}</dt><dd><code>{{ connectionInfo?.rest_endpoint ?? 'Unavailable' }}</code></dd></div><div><dt>{{ t("Remote MCP / Streamable HTTP") }}</dt><dd v-if="connectionInfo?.remote_mcp_endpoint"><code>{{ connectionInfo.remote_mcp_endpoint }}</code></dd><dd v-else>{{ t("Not enabled. Set") }} <code>MCP_TRANSPORT=streamable-http</code> {{ t("to expose the configured loopback endpoint.") }}</dd></div></dl>
      <p class="hint">{{ t("Remote MCP uses the same bearer token and permissions as REST. Keep it private: use TLS and network access controls before exposing it beyond your machine.") }}</p>
      <details :open="selectedProvider === 'chatgpt'"><summary>{{ t("ChatGPT / Codex connection") }}</summary><p>{{ t("For local Codex, start") }} <code>application-tracker-mcp</code> {{ t("with") }} <code>APPLICATION_TRACKER_AGENT_TOKEN</code> {{ t("in its protected environment. Use the same workspace data directory and token as Claude. For ChatGPT, validate a Secure MCP Tunnel or secured HTTPS connection in your workspace; remote availability and write actions depend on the client environment.") }}</p></details>
      <details :open="selectedProvider === 'claude'"><summary>{{ t("Claude / Claude Code connection") }}</summary><p>{{ t("For local Claude Code, use the same stdio command and") }} <code>APPLICATION_TRACKER_AGENT_TOKEN</code>{{ t(". Claude remote connectors need a secured HTTPS endpoint reachable from Anthropic. Verify its authentication flow before connecting; no second tracker identity or Google consent is needed.") }}</p></details>
      <p class="hint">{{ t("See AGENT_CONNECTIONS.md for configuration templates and a connection test checklist. Client connections are unverified until tested in your environment. Conflicting agent edits require review. No inference API keys are required by the tracker.") }}</p>
    </details>
    <details class="panel" :aria-label="t('System status')" aria-live="polite" :aria-busy="connection === 'checking'"><summary>{{ t("System status ·") }} {{ connection === 'connected' ? t("Connected") : connection === 'checking' ? t("Checking…") : t("Disconnected") }}</summary><div class="status-heading"><Button type="button" :disabled="connection === 'checking'" @click="checkConnection">{{ connection === 'checking' ? t("Checking…") : t("Check again") }}</Button></div>
      <p v-if="connection === 'disconnected'" class="at-message error">{{ t("Unable to reach the backend. Make sure it is running, then check again or refresh this page.") }}</p>
      <p v-else-if="connection === 'connected'" class="connected">{{ t("Backend connected. Your local database is ready.") }}</p>
      <p v-else>{{ t("Connecting to your local backend…") }}</p>
      <dl><div><dt>{{ t("Backend version") }}</dt><dd>{{ health?.version ?? t("Unavailable") }}</dd></div><div><dt>{{ t("Database") }}</dt><dd>{{ health ? t("SQLite · Connected") : t("Unavailable") }}</dd></div></dl>
    </details>
    <p v-if="message" class="at-message success" role="status">{{ messageText(String((message) ?? '')) }}</p>
      </template>
      <template #connections>    <MailSyncSettings /><GoogleSettings google-only /><AIConnections />
    <details class="panel"><summary>{{ t("Other integrations") }}</summary><p>{{ t("Mail:") }} {{ integrations?.mail.connected ? t("Connected") : t("Not connected") }}{{ t(". Calendar:") }} {{ integrations?.calendar.connected ? t("Connected") : t("Not connected") }}.</p><p>{{ t("Without a mail provider, email drafts are saved as local notes. Interview calendar files can be downloaded and imported manually. Nothing is sent or added to an external calendar automatically.") }}</p></details>
</template>
    </PageTabs>
  </section>
</template>

<style scoped>
@layer legacy {
summary { cursor:pointer; font-weight:650; }
.panel { background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;padding:24px;margin:20px 0; }.panel p,.hint {color:var(--at-text-muted);font-size:14px;line-height:1.5}.primary {background:var(--at-primary);border-color:var(--at-primary);color:var(--at-primary-contrast)}.permission {display:flex;gap:12px;align-items:flex-start;padding:12px 0;border-top:1px solid var(--at-border);cursor:pointer}.permission input {margin-top:3px}.permission span {display:flex;flex-direction:column;gap:3px}.permission small {color:var(--at-text-muted);font-weight:400}.token-box {margin-top:18px;padding:16px;background:color-mix(in srgb, var(--at-cancelled) 10%, var(--at-surface));border:1px solid color-mix(in srgb, var(--at-cancelled) 10%, var(--at-surface));border-radius:6px}.token-box label {display:block;font-weight:650;margin-bottom:8px}.token-box textarea {width:100%;padding:10px;font:inherit;resize:none;overflow-wrap:anywhere}.success,.panel p.connected {color:var(--at-successful)}.status-heading {display:flex;align-items:center;justify-content:space-between;gap:12px}.panel p.error {color:var(--at-unsuccessful)}.panel dl {margin-top:15px}.connection-list div {display:grid;grid-template-columns:minmax(100px, 220px) minmax(0,1fr);gap:12px;padding:10px 0;border-top:1px solid var(--at-border)}.connection-list dt{font-weight:650}.connection-list dd{margin:0;overflow-wrap:anywhere}.connection-list code{font-size:12px}
}
@media(max-width:600px) { .panel { padding:16px; }.connection-list div { grid-template-columns:1fr; }.connection-list dd { text-align:left; } }
</style>
