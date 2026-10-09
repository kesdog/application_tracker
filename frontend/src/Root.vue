<script setup lang="ts">
import { onMounted, ref } from 'vue'
import App from './App.vue'
import { checkHumanSession, humanSession, signIn, signOut } from './auth'
const password = ref('')
const busy = ref(false)
const error = ref('')
async function login() {
  busy.value = true; error.value = ''
  try { await signIn(password.value); password.value = '' }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to sign in.' }
  finally { busy.value = false }
}
async function logout() {
  error.value = ''
  try { await signOut() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to confirm sign-out. Try again.' }
}
onMounted(checkHumanSession)
</script>

<template>
  <template v-if="humanSession.loaded && humanSession.authenticated"><p v-if="error" class="auth-error" role="alert">{{ error }}</p><App :hosted="humanSession.enabled" @signout="logout" /></template>
  <main v-else class="sign-in"><section><div class="mark" aria-hidden="true">AT</div><h1>Application Tracker</h1><p v-if="humanSession.checking" role="status">Connecting to your workspace…</p>
    <template v-else><p v-if="humanSession.error" class="auth-error" role="alert">{{ humanSession.error }}</p><form v-if="humanSession.loaded" @submit.prevent="login"><h2>Sign in to your workspace</h2><p>Use the workspace password set on your server.</p><label for="workspace-password">Password</label><input id="workspace-password" v-model="password" type="password" autocomplete="current-password" maxlength="1024" required :disabled="busy" /><p v-if="error" class="auth-error" role="alert">{{ error }}</p><button type="submit" :disabled="busy || !password">{{ busy ? 'Signing in…' : 'Sign in' }}</button></form><button v-else type="button" @click="checkHumanSession">Try again</button></template>
  </section></main>
</template>

<style scoped>
.sign-in{box-sizing:border-box;min-height:100dvh;display:grid;place-items:center;padding:24px;color:var(--at-text);background:var(--at-background)}section{box-sizing:border-box;width:min(100%,420px);padding:28px;border:1px solid var(--at-border);border-radius:12px;background:var(--at-surface)}.mark{width:48px;height:48px;display:grid;place-items:center;background:var(--at-primary);color:var(--at-primary-contrast);border-radius:10px;font-weight:700}h1{font-size:24px;margin:20px 0}h2{font-size:19px}p{line-height:1.6;color:var(--at-text-muted)}label{display:block;font-weight:600}input{box-sizing:border-box;width:100%;font:inherit;color:var(--at-text);background:var(--at-surface);padding:12px;margin:8px 0 16px;border:1px solid var(--at-border);border-radius:6px}button{font:inherit;padding:12px 18px;color:var(--at-primary-contrast);background:var(--at-primary);border:0;border-radius:6px;cursor:pointer}button:disabled{opacity:.6}.auth-error{color:var(--at-unsuccessful);padding:12px}input:focus-visible,button:focus-visible{outline:3px solid var(--at-focus);outline-offset:3px}
</style>
