<script setup lang="ts">
import { t, messageText, errorText } from './i18n'

import { onMounted, ref, watch } from 'vue'
import App from './App.vue'
import WelcomeExperience from './components/welcome/WelcomeExperience.vue'
import ProviderSignIn from './components/auth/ProviderSignIn.vue'
import { browserSession, workspaceLogin } from './auth'
const welcome = ref<InstanceType<typeof WelcomeExperience> | null>(null)
const humanSession = browserSession.state
const checkHumanSession = () => workspaceLogin.check()
const password = ref('')
const busy = ref(false)
const googleBusy = ref(false)
const error = ref('')
async function login() {
  if (busy.value || googleBusy.value) return
  busy.value = true; error.value = ''
  try { await workspaceLogin.signIn(password.value); password.value = '' }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to sign in.") }
  finally { busy.value = false }
}
async function logout() {
  error.value = ''
  try { await workspaceLogin.signOut() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to confirm sign-out. Try again.") }
}
onMounted(checkHumanSession)
watch(() => humanSession.authenticated, () => { googleBusy.value = false })
</script>

<template>
  <template v-if="humanSession.loaded && humanSession.authenticated"><p v-if="error" class="auth-error" role="alert">{{ errorText(String((error) ?? '')) }}</p><App :hosted="humanSession.enabled" @signout="logout" @open-guide="welcome?.openGuide()" @open-legal="document => welcome?.openLegal(document)" /></template>
  <main v-else class="sign-in"><section><div class="mark" aria-hidden="true">{{ t("AT") }}</div><h1>{{ t("Application Tracker") }}</h1><p v-if="humanSession.checking" role="status">{{ t("Connecting to your workspace…") }}</p>
    <template v-else><p v-if="humanSession.error" class="auth-error" role="alert">{{ errorText(String((humanSession.error) ?? '')) }}</p><template v-if="humanSession.loaded"><h2>{{ t("Sign in to your workspace") }}</h2><ProviderSignIn :disabled="busy" @busy="googleBusy = $event" /><form @submit.prevent="login"><p class="password-caption">{{ t("Or use your workspace password") }}</p><label for="workspace-password">{{ t("Password") }}</label><input id="workspace-password" v-model="password" type="password" autocomplete="current-password" maxlength="1024" required :disabled="busy || googleBusy" /><p v-if="error" class="auth-error" role="alert">{{ errorText(String((error) ?? '')) }}</p><button type="submit" :disabled="busy || googleBusy || !password">{{ busy ? t("Signing in…") : t("Sign in") }}</button></form></template><button v-else type="button" @click="checkHumanSession">{{ t("Try again") }}</button></template>
  </section></main>
  <WelcomeExperience ref="welcome" :ready="humanSession.loaded && humanSession.authenticated" />
</template>

<style scoped>
.sign-in{box-sizing:border-box;min-height:100dvh;display:grid;place-items:center;padding:24px;color:var(--at-text);background:var(--at-background)}section{box-sizing:border-box;width:min(100%,420px);padding:28px;border:1px solid var(--at-border);border-radius:12px;background:var(--at-surface)}.mark{width:48px;height:48px;display:grid;place-items:center;background:var(--at-primary);color:var(--at-primary-contrast);border-radius:10px;font-weight:700}h1{font-size:24px;margin:20px 0}h2{font-size:19px}p{line-height:1.6;color:var(--at-text-muted)}label{display:block;font-weight:600}input{box-sizing:border-box;width:100%;font:inherit;color:var(--at-text);background:var(--at-surface);padding:12px;margin:8px 0 16px;border:1px solid var(--at-border);border-radius:6px}button{font:inherit;padding:12px 18px;color:var(--at-primary-contrast);background:var(--at-primary);border:0;border-radius:6px;cursor:pointer}button:disabled{opacity:.6}.auth-error{color:var(--at-unsuccessful);padding:12px}input:focus-visible,button:focus-visible{outline:3px solid var(--at-focus);outline-offset:3px}
</style>

<style scoped>
form>button{width:100%;min-height:48px}.password-caption{border-top:1px solid var(--at-border);padding-top:20px;font-size:14px}section{min-width:0}@media(max-width:480px){.sign-in{padding:16px}section{padding:24px 20px}}
</style>
