<script setup lang="ts">
import { t, messageText } from '../../i18n'

import { computed, ref } from 'vue'
const props = defineProps<{ disabled?: boolean; googleLabel?: string; googleUser?: string | null; googleStatus?: string; googleOnly?: boolean }>()
defineEmits<{ google: []; chatgpt: []; claude: []; googleLogout: [] }>()
const googleButton = ref<HTMLButtonElement | null>(null)
const googleState = computed(() => {
  if (props.googleStatus === 'CONNECTED' || props.googleStatus === 'PARTIAL') return t("Connected")
  if (props.googleStatus === 'RECONNECT_REQUIRED') return t("Reconnect required")
  if (props.googleStatus === 'CREDENTIALS_UNAVAILABLE') return t("Connection unavailable")
  return t("Not connected")
})
defineExpose({ focusGoogle: () => googleButton.value?.focus() })
</script>

<template>
  <div class="provider-buttons" :aria-label="t('Account connections')">
    <button v-if="!googleUser" ref="googleButton" type="button" :disabled="disabled" @click="$emit('google')"><img :src="'/icons/google.png'" alt="" width="24" height="24" /><span>{{ googleLabel || t("Connect Google") }}</span></button>
    <button v-if="!googleOnly" type="button" :disabled="disabled" @click="$emit('chatgpt')"><img class="chatgpt" :src="'/icons/chatgpt.svg'" alt="" width="24" height="24" /><span>{{ t("Connect ChatGPT") }}</span></button>
    <button v-if="!googleOnly" type="button" :disabled="disabled" @click="$emit('claude')"><img :src="'/icons/claude.svg'" alt="" width="24" height="24" /><span>{{ t("Connect Claude") }}</span></button>
    <div v-if="googleUser" class="google-account" role="group" :aria-label="t('Google account')">
      <img :src="'/icons/google.png'" alt="" width="24" height="24" />
      <div class="google-identity"><strong>{{ t("Google") }}</strong><span role="status">{{ googleState }} · {{ googleUser }}</span></div>
      <button class="google-logout" type="button" :disabled="disabled" :aria-label="t('Log out of Google in Application Tracker')" @click="$emit('googleLogout')">{{ t("Log out") }}</button>
    </div>
  </div>
</template>

<style scoped>
.provider-buttons{display:grid;gap:12px}.provider-buttons button{box-sizing:border-box;display:flex;align-items:center;gap:12px;width:100%;min-height:48px;padding:12px 16px;border:1px solid var(--at-border);border-radius:8px;color:var(--at-text);background:var(--at-surface);font:inherit;font-weight:600;text-align:left;cursor:pointer}.provider-buttons button:hover{border-color:var(--at-primary)}.provider-buttons button:focus-visible{outline:3px solid var(--at-focus);outline-offset:3px}.provider-buttons button:disabled{opacity:.65;cursor:wait}.provider-buttons img{flex:none;object-fit:contain}.chatgpt{filter:brightness(0)}:global([data-theme="dark"] .provider-buttons .chatgpt){filter:none}
</style>

<style scoped>
.google-account{display:flex;align-items:center;gap:12px;min-width:0;padding:12px 16px;border:1px solid var(--at-border);border-radius:8px;color:var(--at-text);background:var(--at-surface)}.google-identity{display:grid;gap:4px;min-width:0;flex:1}.google-identity [role=status]{font-size:14px;color:var(--at-text-muted);overflow-wrap:anywhere}.google-account .google-logout{width:auto;flex:none;justify-content:center;font-weight:500}.google-account img{flex:none}@media(max-width:420px){.google-account{flex-wrap:wrap}.google-account .google-logout{width:100%}}
</style>
