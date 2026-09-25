<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAgentSettings, getIntegrationStatus, regenerateAgentToken, saveAgentPermissions, type AgentPermissions, type AgentSettings, type IntegrationStatus } from './api'

const settings = ref<AgentSettings | null>(null)
const integrations = ref<IntegrationStatus | null>(null)
const token = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const message = ref('')
const permissions = ref<AgentPermissions>({ read: true, create: false, edit: false, draft: false, tasks: false, interviews: false })
const labels: { key: keyof AgentPermissions; label: string; help: string }[] = [
  { key: 'read', label: 'Read', help: 'View applications, activity, and upcoming work.' },
  { key: 'create', label: 'Create', help: 'Create applications.' },
  { key: 'edit', label: 'Edit', help: 'Change application details and status.' },
  { key: 'draft', label: 'Draft', help: 'Create notes and follow-ups, and record a follow-up as sent.' },
  { key: 'tasks', label: 'Tasks', help: 'Create and complete tasks.' },
  { key: 'interviews', label: 'Interviews', help: 'Schedule and update interviews.' },
]

async function load() {
  loading.value = true; error.value = ''
  try { settings.value = await getAgentSettings(); permissions.value = { ...settings.value.permissions }; integrations.value = await getIntegrationStatus() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load agent settings.' }
  finally { loading.value = false }
}

async function generate() {
  saving.value = true; error.value = ''; message.value = ''; token.value = ''
  try {
    const result = await regenerateAgentToken()
    settings.value = result; permissions.value = { ...result.permissions }; token.value = result.token
    message.value = 'Copy this token now. It will disappear when you leave this page.'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to generate token.' }
  finally { saving.value = false }
}

async function save() {
  saving.value = true; error.value = ''; message.value = ''
  try { settings.value = await saveAgentPermissions(permissions.value); message.value = 'Permissions saved.' }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to save permissions.' }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <section aria-labelledby="agent-settings-title">
    <p class="eyebrow">Local settings</p><h2 id="agent-settings-title">Agent access</h2>
    <p class="intro">Create a token for an external agent, then choose what it can do. Agents cannot delete applications.</p>
    <p v-if="loading" role="status">Loading agent settings…</p><p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="settings">
      <section class="panel"><h3>Access token</h3><p>{{ settings.configured ? 'An agent token is configured.' : 'No agent token has been created.' }}</p>
        <button type="button" class="primary" :disabled="saving" @click="generate">{{ settings.configured ? 'Regenerate token' : 'Generate token' }}</button>
        <p v-if="settings.configured" class="hint">Regenerating invalidates the previous token immediately.</p>
        <div v-if="token" class="token-box"><label for="agent-token">New token — shown once</label><textarea id="agent-token" :value="token" readonly rows="3" @focus="($event.target as HTMLTextAreaElement).select()"></textarea><p>Copy it into your agent's secure configuration. This page does not store the plaintext token.</p></div>
      </section>
      <form class="panel" @submit.prevent="save"><h3>Permissions</h3><p class="hint">Changes apply to REST and MCP calls immediately.</p>
        <label v-for="item in labels" :key="item.key" class="permission"><input v-model="permissions[item.key]" type="checkbox" :disabled="saving || !settings.configured" /><span><strong>{{ item.label }}</strong><small>{{ item.help }}</small></span></label>
        <button class="primary" type="submit" :disabled="saving || !settings.configured">Save permissions</button>
      </form>
    </template>
    <section class="panel"><h3>Integrations</h3><p>Mail: {{ integrations?.mail.connected ? 'Connected' : 'Not connected' }}. Calendar: {{ integrations?.calendar.connected ? 'Connected' : 'Not connected' }}.</p><p>Without a mail provider, email drafts are saved as local notes. Interview calendar files can be downloaded and imported manually. Nothing is sent or added to an external calendar automatically.</p></section>
    <p v-if="message" class="success" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.panel { background:#fff;border:1px solid #dce2e9;border-radius:8px;padding:24px;margin:20px 0; }.panel p,.hint {color:#576678;font-size:14px;line-height:1.5}.primary {background:#263e5c;border-color:#263e5c;color:#fff}.permission {display:flex;gap:12px;align-items:flex-start;padding:12px 0;border-top:1px solid #e5e9ee;cursor:pointer}.permission input {margin-top:3px}.permission span {display:flex;flex-direction:column;gap:3px}.permission small {color:#576678;font-weight:400}.token-box {margin-top:18px;padding:16px;background:#fff1de;border:1px solid #efcca1;border-radius:6px}.token-box label {display:block;font-weight:650;margin-bottom:8px}.token-box textarea {width:100%;padding:10px;font:inherit;resize:none;overflow-wrap:anywhere}.success {color:#216344}
</style>
