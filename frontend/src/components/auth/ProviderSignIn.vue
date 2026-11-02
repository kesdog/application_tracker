<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { workspaceLogin } from '../../auth'
import { identityRequest, loadGoogleIdentity, type GoogleIdentity } from '../../googleIdentity'
import { themeMode } from '../../settings/appearanceStore'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean] }>()
const host = ref<HTMLElement | null>(null)
const loading = ref(true)
const signingIn = ref(false)
const ready = ref(false)
const error = ref('')
const help = ref<'google' | 'claude' | 'chatgpt' | null>(null)
let identity: GoogleIdentity | undefined
let observer: ResizeObserver | undefined
let active = true
let attempt = 0
let state = ''
let lastWidth = 0

function render() {
  if (!host.value || !identity) return
  // GIS renders at 40px. Uniform scaling preserves its design and yields a 44px target.
  const width = Math.min(400, Math.floor(host.value.clientWidth / 1.1))
  if (width < 200) return
  lastWidth = width
  host.value.replaceChildren()
  identity.renderButton(host.value, { type: 'standard', theme: themeMode.value === 'dark' ? 'filled_black' : 'outline', size: 'large', text: 'continue_with', width })
}
async function prepare() {
  const current = ++attempt
  loading.value = true; error.value = ''; ready.value = false
  try {
    const provider = await identityRequest<unknown>('/api/auth/providers').then(body => {
      const value = (body as { google?: { available?: unknown; client_id?: unknown } })?.google
      if (typeof value?.available !== 'boolean' || (value.available && (typeof value.client_id !== 'string' || !value.client_id))) throw new Error(t("Unexpected provider configuration. Use the workspace password or try again."))
      return { available: value.available, client_id: typeof value.client_id === 'string' ? value.client_id : null }
    })
    if (!active || current !== attempt) return
    if (!provider.available) return
    identity = await loadGoogleIdentity()
    if (!active || current !== attempt) return
    const challenge = await identityRequest<{ state: string; nonce: string }>('/api/auth/google/start', true)
    if (!active || current !== attempt) return
    state = challenge.state
    identity.initialize({ client_id: provider.client_id!, nonce: challenge.nonce, auto_select: false, ux_mode: 'popup', callback: response => { if (active && current === attempt) void finish(response.credential) } })
    ready.value = true
    await nextTick()
    if (active) render()
  } catch (reason) {
    if (active && current === attempt) error.value = reason instanceof Error ? reason.message : t("Google sign-in failed.")
  } finally { if (active && current === attempt) loading.value = false }
}
async function finish(credential: string) {
  if (signingIn.value || props.disabled) return
  signingIn.value = true; emit('busy', true); error.value = ''
  try { await workspaceLogin.signInGoogle(credential, state) }
  catch (reason) {
    if (active) { error.value = reason instanceof Error ? reason.message : t("Google sign-in failed."); ready.value = false }
  } finally { signingIn.value = false; emit('busy', false) }
}
onMounted(() => {
  void prepare()
  observer = new ResizeObserver(() => {
    if (host.value && Math.min(400, Math.floor(host.value.clientWidth / 1.1)) !== lastWidth) render()
  })
  if (host.value) observer.observe(host.value)
})
watch(themeMode, render)
onBeforeUnmount(() => { active = false; attempt++; observer?.disconnect() })
</script>

<template>
  <div class="providers">
    <div v-show="ready && !signingIn" class="google-target" :inert="disabled || undefined"><div ref="host" class="google-render" /></div>
    <p v-if="loading || signingIn" role="status">{{ signingIn ? t("Signing in with Google…") : t("Preparing Google sign-in…") }}</p>
    <button v-if="!loading && !ready && !signingIn" class="provider-control" type="button" :disabled="disabled" :aria-expanded="help === 'google'" aria-controls="google-help" @click="help = help === 'google' ? null : 'google'"><img :src="'/icons/google.png'" alt="" width="22" height="22" /><span>{{ t("Continue with Google") }}</span></button>
    <div v-if="help === 'google'" id="google-help" class="provider-help"><p>{{ t("The workspace owner must enable Google sign-in and allow your account. You can use the workspace password below.") }}</p><a href="https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid" target="_blank" rel="noopener noreferrer">{{ t("Google sign-in requirements") }}</a></div>
    <p v-if="error" class="provider-error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <button v-if="error" type="button" class="provider-control" :disabled="disabled || loading" @click="prepare">{{ t("Retry Google sign-in") }}</button>
    <p v-if="ready" class="provider-caption">{{ t("Google signs you in only. Gmail and Drive are optional in Settings.") }}</p>
    <button class="provider-control" type="button" :disabled="disabled || signingIn" :aria-expanded="help === 'claude'" aria-controls="claude-help" @click="help = help === 'claude' ? null : 'claude'"><img class="claude-symbol" :src="'/icons/claude.svg'" alt="" width="22" height="22" /><span>{{ t("Connect Claude") }}</span><small>{{ t("Connector") }}</small></button>
    <div v-if="help === 'claude'" id="claude-help" class="provider-help"><p>{{ t("Claude connects to your tracker through MCP. Sign in to this workspace first, then open Settings → Agent access for connection instructions. A Claude subscription does not sign you in here.") }}</p><a href="https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities" target="_blank" rel="noopener noreferrer">{{ t("Supported Claude connections") }}</a></div>
    <button class="provider-control" type="button" :disabled="disabled || signingIn" :aria-expanded="help === 'chatgpt'" aria-controls="chatgpt-help" @click="help = help === 'chatgpt' ? null : 'chatgpt'"><img class="chatgpt-symbol" :src="'/icons/chatgpt.svg'" alt="" width="22" height="22" /><span>{{ t("Connect ChatGPT") }}</span><small>{{ t("Connector") }}</small></button>
    <div v-if="help === 'chatgpt'" id="chatgpt-help" class="provider-help"><p>{{ t("Sign in to this workspace first. Onboarding and Settings → Connections offer direct ChatGPT linking on a local installation. For a hosted workspace, use the ChatGPT connector in Settings → Agent & system. ChatGPT linking does not sign you into this workspace.") }}</p><a href="https://developers.openai.com/siwc/token-sharing-open-source/sign-in" target="_blank" rel="noopener noreferrer">{{ t("ChatGPT linking requirements") }}</a></div>
  </div>
</template>

<style scoped>
.providers{display:grid;gap:12px;margin:24px 0}.provider-control{box-sizing:border-box;width:100%;min-height:48px;display:flex;align-items:center;gap:12px;padding:10px 14px;font:inherit;font-weight:600;text-align:left;color:var(--at-text);background:var(--at-surface);border:1px solid var(--at-border);border-radius:8px;cursor:pointer}.provider-control:hover{border-color:var(--at-primary)}.provider-control:focus-visible,.provider-help a:focus-visible{outline:3px solid var(--at-focus);outline-offset:3px}.provider-control:disabled{opacity:.65;cursor:wait}.provider-control small{margin-left:auto;color:var(--at-text-muted);font-size:11px;font-weight:400}.chatgpt-symbol{filter:brightness(0)}:global([data-theme="dark"] .chatgpt-symbol){filter:none}.google-letter{color:#4285f4;font-size:23px;font-weight:700;width:22px}.provider-help{padding:0 12px 12px;border-left:2px solid var(--at-border);font-size:14px;overflow-wrap:anywhere}.provider-help p,.provider-caption{color:var(--at-text-muted);line-height:1.6;margin:0 0 8px}.provider-help a{display:inline-flex;align-items:center;min-height:44px;color:var(--at-primary)}.provider-error{color:var(--at-unsuccessful);line-height:1.6;margin:0}.provider-caption{font-size:13px;margin:0}.google-target{min-height:44px}.google-render{width:100%;transform:scale(1.1);transform-origin:top left}.providers>p[role=status]{color:var(--at-text-muted);margin:0;min-height:44px;display:flex;align-items:center}
</style>
