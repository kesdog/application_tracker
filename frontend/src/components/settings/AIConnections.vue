<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { nextTick, onMounted, ref, useId, watch } from 'vue'
import Button from 'primevue/button'
import { ApiRequestError } from '../../api'
import { connectClaude, disconnectAI, getAIConnections, getAIModels, startChatGPT, testAI, type AIConnections, type AIProvider } from '../../aiConnections'

const connections = ref<AIConnections | null>(null)
const emit = defineEmits<{ connector: [provider: AIProvider] }>()
const id = useId()
const busy = ref(false)
const key = ref('')
const account = ref<string | null>(null)
const error = ref('')
const errorMessage = ref<HTMLElement | null>(null)
watch(error, async value => { if (value) { await nextTick(); errorMessage.value?.focus() } })
const notice = ref('')
const retryAfter = ref<number | null>(null)
const models = ref<Record<AIProvider, { id: string; name: string }[]>>({ chatgpt: [], claude: [] })
const selected = ref<Record<AIProvider, string>>({ chatgpt: '', claude: '' })

async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''; retryAfter.value = null
  try { await action() }
  catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("Unable to connect AI. Try again.")
    if (reason instanceof ApiRequestError) retryAfter.value = reason.retryAfter ?? null
  } finally { busy.value = false }
}
function load() { return perform(async () => {
  connections.value = await getAIConnections()
  account.value = connections.value.chatgpt.account
}) }
function chatgpt() { return perform(async () => {
  const result = await startChatGPT(account.value)
  window.location.assign(result.authorization_url)
}) }
function claude() { return perform(async () => {
  try { connections.value = await connectClaude(key.value.trim()); models.value.claude = []; selected.value.claude = ''; notice.value = t("Claude API key verified and saved securely.") }
  finally { key.value = '' }
}) }
function disconnect(provider: AIProvider) { return perform(async () => {
  const result = await disconnectAI(provider)
  connections.value = result.connections; notice.value = result.message
  account.value = result.connections.chatgpt.account
  models.value[provider] = []; selected.value[provider] = ''
}) }
function listModels(provider: AIProvider) { return perform(async () => {
  models.value[provider] = []; selected.value[provider] = ''
  models.value[provider] = await getAIModels(provider)
  selected.value[provider] = models.value[provider][0]?.id ?? ''
  if (!models.value[provider].length) notice.value = t("This account has no available models. Check its permissions and plan.")
}) }
function test(provider: AIProvider) { return perform(async () => {
  notice.value = (await testAI(provider, selected.value[provider])).message
}) }
onMounted(async () => {
  await load()
  const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const result = query.get('ai_result')
  if (result === 'connected') notice.value = t("ChatGPT linked. You can check its AI access below.")
  else if (result) error.value = result === 'permission' ? t("ChatGPT authorization was cancelled or access was declined. Connect again whenever you are ready.") : t("ChatGPT linking did not complete. Try connecting again; your previous account is kept.")
  if (result) {
    query.delete('ai_result')
    window.history.replaceState(null, '', window.location.pathname + window.location.search + '#/settings?' + query.toString())
  }
})
</script>

<template>
  <section :id="`${id}-ai-connections`" class="ai-panel" :aria-labelledby="`${id}-ai-title`" :aria-busy="busy">
    <h3 :id="`${id}-ai-title`">{{ t("AI accounts · optional") }}</h3>
    <p>{{ t("Connect AI access for this installation. Linking does not start AI requests or grant an agent access to your applications.") }}</p>
    <p v-if="!connections && !error" role="status">{{ t("Loading AI connections…") }}</p>
    <p v-if="error" ref="errorMessage" tabindex="-1" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}<span v-if="retryAfter !== null"> {{ t("Try again in") }} {{ retryAfter }} {{ t("seconds.") }}</span></p>
    <p v-if="notice" class="at-message success" role="status">{{ messageText(String((notice) ?? '')) }}</p>
    <template v-if="connections">
      <section class="provider" :aria-labelledby="`${id}-chatgpt-title`">
        <h4 :id="`${id}-chatgpt-title`"><img class="chatgpt" :src="'/icons/chatgpt.svg'" alt="" width="24" height="24" />{{ t("ChatGPT") }}</h4>
        <p role="status">{{ connections.chatgpt.connected ? t("Linked · {p0}", { p0: connections.chatgpt.email || 'ChatGPT account' }) : t("Not linked") }}</p>
        <template v-if="connections.chatgpt.available">
          <p>{{ t("Sign in with ChatGPT to allow eligible plan usage. Review and manage this app's allowance in ChatGPT.") }}</p>
          <label v-if="connections.chatgpt.accounts.length">{{ t("Account to connect") }}
            <select v-model="account" :disabled="busy"><option :value="null">{{ t("Add another ChatGPT account") }}</option><option v-for="item in connections.chatgpt.accounts" :key="item.id" :value="item.id">{{ messageText(String((item.label) ?? '')) }}</option></select>
          </label>
          <div class="actions"><Button type="button" class="chatgpt-signin" :disabled="busy" @click="chatgpt"><img class="chatgpt" :src="'/icons/chatgpt.svg'" alt="" width="22" height="22" />{{ t("Continue with ChatGPT") }}</Button><Button v-if="connections.chatgpt.connected" type="button" severity="secondary" :disabled="busy" @click="disconnect('chatgpt')">{{ t("Disconnect ChatGPT") }}</Button></div>
          <p v-if="connections.chatgpt.connected && !connections.chatgpt.can_use" role="alert">{{ t("Your identity is linked, but ChatGPT plan usage was not granted. Continue with ChatGPT to review permissions.") }}</p>
        </template>
        <p v-else>{{ t("Direct ChatGPT linking is available in the local installation at http://127.0.0.1. For this workspace, use the ChatGPT connector setup below.") }}</p>
        <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">{{ t("Manage ChatGPT usage and app access") }}</a>
      </section>
      <section class="provider" :aria-labelledby="`${id}-claude-title`">
        <h4 :id="`${id}-claude-title`"><img :src="'/icons/claude.svg'" alt="" width="24" height="24" />{{ t("Claude") }}</h4>
        <p role="status">{{ connections.claude.connected ? t("API key connected") : t("Not connected") }}</p>
        <p>{{ t("Claude supports an API key connection here. Claude subscriptions and API billing are separate. To use Claude with your existing subscription, use the connector setup below.") }}</p>
        <form @submit.prevent="claude"><label :for="`${id}-claude-key`">{{ t("Claude Console API key") }}</label><input :id="`${id}-claude-key`" v-model="key" type="password" autocomplete="off" spellcheck="false" :disabled="busy" maxlength="4096" />
          <div class="actions"><Button type="submit" :disabled="busy || key.trim().length < 10">{{ connections.claude.connected ? t("Replace Claude API key") : t("Connect Claude API") }}</Button><Button v-if="connections.claude.connected" type="button" severity="secondary" :disabled="busy" @click="disconnect('claude')">{{ t("Disconnect Claude") }}</Button></div>
        </form>
        <a href="https://platform.claude.com/settings/billing" target="_blank" rel="noopener noreferrer">{{ t("Manage Claude API billing") }}</a>
      </section>
      <details v-for="provider in (['chatgpt', 'claude'] as const)" v-show="provider === 'chatgpt' ? connections.chatgpt.can_use : connections.claude.connected" :key="provider" class="provider">
        <summary>{{ t("Check") }} {{ provider === 'chatgpt' ? t("ChatGPT") : t("Claude") }} {{ t("AI access") }}</summary>
        <p>{{ t("Refreshing models does not generate text. The AI test sends only “Reply with OK.” and uses a small amount of your plan allowance or API credits.") }}</p>
        <Button type="button" severity="secondary" :disabled="busy" @click="listModels(provider)">{{ t("Refresh") }} {{ provider === 'chatgpt' ? t("ChatGPT") : t("Claude") }} {{ t("models") }}</Button>
        <label v-if="models[provider].length">{{ t("Model") }}<select v-model="selected[provider]" :disabled="busy"><option v-for="model in models[provider]" :key="model.id" :value="model.id">{{ model.name }}</option></select></label>
        <Button v-if="models[provider].length" type="button" :disabled="busy || !selected[provider]" @click="test(provider)">{{ t("Test") }} {{ provider === 'chatgpt' ? t("ChatGPT") : t("Claude") }} {{ t("AI access") }}</Button>
      </details>
      <p>{{ t("Your credentials stay in this installation's secure store. Disconnecting removes its saved tokens or key. Local tracking remains available when AI usage runs out.") }}</p>
      <div class="actions"><a href="#/settings?tab=agent&amp;provider=chatgpt" @click="emit('connector', 'chatgpt')">{{ t("ChatGPT connector setup") }}</a><a href="#/settings?tab=agent&amp;provider=claude" @click="emit('connector', 'claude')">{{ t("Claude connector setup") }}</a></div>
    </template>
    <Button type="button" text severity="secondary" :disabled="busy" @click="load">{{ t("Refresh AI connections") }}</Button>
  </section>
</template>

<style scoped>
.ai-panel{margin:20px 0;padding:24px;background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;min-width:0}.ai-panel p{color:var(--at-text-muted);line-height:1.6;overflow-wrap:anywhere}.ai-panel .error{color:var(--at-unsuccessful)}.provider{border-top:1px solid var(--at-border);padding-block:16px}h4{display:flex;align-items:center;gap:10px;margin:0 0 10px;font-size:18px}label{display:block;font-weight:600}input,select{box-sizing:border-box;display:block;max-width:100%;width:100%;margin:8px 0 16px;padding:12px;border:1px solid var(--at-border);border-radius:6px;font:inherit;background:var(--at-surface);color:var(--at-text)}.actions{display:flex;flex-wrap:wrap;gap:12px}.ai-panel a{display:inline-flex;align-items:center;min-height:44px;color:var(--at-primary);overflow-wrap:anywhere}summary{font-weight:600;cursor:pointer;min-height:44px}a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--at-focus);outline-offset:3px}.chatgpt{filter:brightness(0)}:global([data-theme="dark"] .chatgpt){filter:none}@media(max-width:540px){.ai-panel{padding:16px}.actions{flex-direction:column}}
</style>

<style scoped>
.ai-panel .chatgpt-signin{min-height:44px;background:#fff;color:#000;border:1px solid #888}.ai-panel .chatgpt-signin:hover{background:#f5f5f5;color:#000}:global([data-theme="dark"] .ai-panel .chatgpt-signin){background:#171717;color:#fff;border-color:#888}:global([data-theme="dark"] .ai-panel .chatgpt-signin:hover){background:#252525;color:#fff}
</style>
