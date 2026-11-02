<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { computed, nextTick, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import LegalNotice from './LegalNotice.vue'
import GoogleSettings from '../settings/GoogleSettings.vue'
import AIConnections from '../settings/AIConnections.vue'
import { appearanceSaveError, setThemeMode, themeMode } from '../../settings/appearanceStore'
import { readPreference, writePreference } from '../../settings/localPreferences'

const props = defineProps<{ ready: boolean }>()
const guideKey = 'application-tracker:welcome:v1'
const noticeKey = 'application-tracker:storage-notice:v1'
const resumeKey = 'application-tracker:welcome-step:v1'
const guideSeen = ref(readPreference(guideKey) === true)
const noticeSeen = ref(readPreference(noticeKey) === true)
const storageError = ref('')
const panel = ref<'guide' | 'terms' | 'privacy' | null>(null)
const returnToGuide = ref(false)
const step = ref(0)
const stepHeading = ref<HTMLElement | null>(null)
const steps = ['Welcome', 'How it works', 'Connect accounts', 'Make it yours']
const title = computed(() => panel.value === 'guide' ? steps[step.value] : panel.value === 'terms' ? t("Terms and conditions") : t("Privacy, cookies & storage"))
watch(step, async () => { writePreference(resumeKey, step.value); await nextTick(); stepHeading.value?.focus() })

watch(() => props.ready, ready => {
  if (ready && !guideSeen.value && !panel.value) openGuide(true)
  if (!ready && panel.value === 'guide') panel.value = null
}, { immediate: true })

function openGuide(resume = false) {
  if (!props.ready) return
  const saved = resume ? readPreference(resumeKey) : 0
  step.value = typeof saved === 'number' && Number.isInteger(saved) && saved >= 0 && saved < steps.length ? saved : 0
  returnToGuide.value = false
  panel.value = 'guide'
}
function openLegal(document: 'terms' | 'privacy') {
  returnToGuide.value = panel.value === 'guide' || returnToGuide.value
  panel.value = document
}
function remember(key: string) {
  if (!writePreference(key, true)) storageError.value = t("Your browser could not save this choice. You can continue; the guide or notice may appear again on your next visit.")
}
function dismissGuide() {
  guideSeen.value = true
  remember(guideKey)
  writePreference(resumeKey, 0)
  panel.value = null
}
function closePanel() {
  if (panel.value === 'guide') dismissGuide()
  else if (returnToGuide.value && props.ready) { panel.value = 'guide'; returnToGuide.value = false }
  else {
    panel.value = null; returnToGuide.value = false
    if (props.ready && !guideSeen.value) openGuide()
  }
}
function finish(destination?: string) {
  dismissGuide()
  if (destination) window.location.hash = destination
}
function dismissNotice() { noticeSeen.value = true; remember(noticeKey) }
defineExpose({ openGuide, openLegal })
</script>

<template>
  <div v-if="!ready" class="public-help" :aria-label="t('Workspace information')">
    <Button type="button" text severity="secondary" @click="openLegal('terms')">{{ t("Terms and conditions") }}</Button>
    <Button type="button" text severity="secondary" @click="openLegal('privacy')">{{ t("Privacy & cookies") }}</Button>
  </div>

  <section v-if="!noticeSeen && !panel" class="storage-notice" aria-labelledby="storage-notice-title">
    <div><h2 id="storage-notice-title">{{ t("Cookies & storage, explained") }}</h2><p>{{ t("We use browser storage to remember your preferences and functional cookies for workspace login or a Google connection. The app has no advertising or analytics trackers.") }}</p></div>
    <div class="notice-actions"><Button type="button" severity="secondary" @click="openLegal('privacy')">{{ t("Read details") }}</Button><Button type="button" @click="dismissNotice">{{ t("Got it") }}</Button></div>
  </section>
  <p v-if="storageError" class="storage-error at-message warning" role="status">{{ errorText(storageError) }}</p>

  <Dialog :visible="panel !== null" modal :header="messageText(String((title) ?? ''))" :draggable="false" :style="{ width: 'min(680px, calc(100vw - 24px))' }" :dismissable-mask="false" @update:visible="value => { if (!value) closePanel() }">
    <div v-if="panel === 'guide'" class="welcome-guide">
      <nav :aria-label="t('Welcome progress')"><ol class="welcome-progress"><li v-for="(label, index) in steps" :key="label" :aria-current="index === step ? 'step' : undefined" :class="{ current: index === step, done: index < step }"><span>{{ index + 1 }}</span>{{ messageText(String((label) ?? '')) }}</li></ol></nav>
      <div v-if="step === 0" class="welcome-step">
        <div class="welcome-mark" aria-hidden="true"><i class="pi pi-briefcase" /></div>
        <h2 ref="stepHeading" tabindex="-1">{{ t("A calmer place for your job search.") }}</h2>
        <p>{{ t("Keep applications, interviews, and the next small step together in one workspace.") }}</p>
        <div class="welcome-callout"><strong>{{ t("Start without an account connection") }}</strong><p>{{ t("No Google or AI sign-in is needed to track applications. Connect optional services later, whenever they are useful.") }}</p></div>
      </div>
      <div v-else-if="step === 1" class="welcome-step">
        <h2 ref="stepHeading" tabindex="-1">{{ t("From application to next action.") }}</h2>
        <ul class="workflow-list">
          <li><i class="pi pi-plus-circle" aria-hidden="true" /><div><strong>{{ t("Save an application") }}</strong><p>{{ t("Add the company, role, and original application date. Fill in the rest as you go.") }}</p></div></li>
          <li><i class="pi pi-calendar" aria-hidden="true" /><div><strong>{{ t("Keep the next step in sight") }}</strong><p>{{ t("Use tasks, interviews, and your dashboard to keep track of what is due.") }}</p></div></li>
          <li><i class="pi pi-envelope" aria-hidden="true" /><div><strong>{{ t("Review every follow-up") }}</strong><p>{{ t("Prepare a draft, check it, then send it yourself. Creating a draft or marking it sent does not deliver email.") }}</p></div></li>
        </ul>
      </div>
      <div v-else-if="step === 2" class="welcome-step">
        <h2 ref="stepHeading" tabindex="-1">{{ t("Connect the accounts you want to use.") }}</h2>
        <p>{{ t("Google sign-in for a hosted workspace is offered on its login screen. Here you can link Google for optional Gmail and Drive access, and connect ChatGPT or Claude for AI access. You can skip every connection.") }}</p>
        <GoogleSettings google-only onboarding />
        <AIConnections @connector="provider => finish(`#/settings?tab=agent&provider=${provider}`)" />
      </div>
      <div v-else class="welcome-step">
        <h2 ref="stepHeading" tabindex="-1">{{ t("Your workspace, your pace.") }}</h2>
        <fieldset class="theme-choice"><legend>{{ t("Choose an appearance") }}</legend><label :class="{ selected: themeMode === 'light' }"><input type="radio" name="welcome-theme" value="light" :checked="themeMode === 'light'" @change="setThemeMode('light')" /><i class="pi pi-sun" aria-hidden="true" /> {{ t("Light · Paper") }}</label><label :class="{ selected: themeMode === 'dark' }"><input type="radio" name="welcome-theme" value="dark" :checked="themeMode === 'dark'" @change="setThemeMode('dark')" /><i class="pi pi-moon" aria-hidden="true" /> {{ t("Dark · Midnight") }}</label></fieldset>
        <p v-if="appearanceSaveError" class="at-message warning" role="status">{{ messageText(String((appearanceSaveError) ?? '')) }}</p>
        <div class="welcome-callout"><strong>{{ t("Connections are always optional") }}</strong><p>{{ t("Google, sync, agent access, and phone notifications live in Settings. You choose which features and permissions to enable.") }}</p><Button type="button" text @click="finish('#/settings')">{{ t("Explore optional connections") }}</Button></div>
        <p class="welcome-small">{{ t("You can reopen this guide from the footer. Your records live on the device or server running this workspace; use Export to keep a copy.") }}</p>
      </div>
      <div class="welcome-documents"><Button type="button" text severity="secondary" @click="openLegal('terms')">{{ t("Terms and conditions") }}</Button><Button type="button" text severity="secondary" @click="openLegal('privacy')">{{ t("Privacy & cookies") }}</Button></div>
    </div>
    <LegalNotice v-else-if="panel === 'terms' || panel === 'privacy'" :document="panel" />
    <template #footer>
      <div v-if="panel === 'guide'" class="welcome-actions">
        <Button type="button" text severity="secondary" @click="dismissGuide">{{ t("Skip for now") }}</Button>
        <div><Button v-if="step > 0" type="button" severity="secondary" @click="step--">{{ t("Back") }}</Button><Button v-if="step < steps.length - 1" type="button" @click="step++">{{ t("Next") }}</Button><Button v-else type="button" @click="finish()">{{ t("Start tracking") }}</Button></div>
      </div>
      <Button v-else type="button" @click="closePanel">{{ returnToGuide && ready ? t("Back to guide") : t("Close") }}</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.welcome-guide { line-height: 1.6; }
.welcome-progress { display: flex; justify-content: space-between; gap: 10px; padding: 0; margin: 0 0 28px; list-style: none; }
.welcome-progress li { display: flex; align-items: center; gap: 7px; color: var(--at-text-muted); font-size: 12px; }
.welcome-progress li span { display: grid; place-items: center; border: 1px solid var(--at-border); width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0; }
.welcome-progress .current { color: var(--at-primary); font-weight: 700; }
.welcome-progress .current span, .welcome-progress .done span { background: var(--at-primary); color: var(--at-primary-contrast); border-color: var(--at-primary); }
.welcome-step { min-height: 300px; }
.welcome-step h2 { font-size: clamp(23px, 4vw, 30px); line-height: 1.2; letter-spacing: -.025em; margin: 16px 0; }
.welcome-step p { color: var(--at-text-muted); margin: 8px 0 16px; }
.welcome-mark { display: grid; place-items: center; width: 56px; height: 56px; border-radius: 14px; background: var(--at-primary); color: var(--at-primary-contrast); font-size: 24px; }
.welcome-callout { padding: 16px 18px; border: 1px solid var(--at-border); border-radius: 10px; background: var(--at-surface-muted); margin: 22px 0 16px; }
.welcome-callout p { margin-bottom: 0; }
.workflow-list { padding: 0; list-style: none; display: grid; gap: 20px; margin: 24px 0; }
.workflow-list li { display: flex; gap: 16px; }
.workflow-list i { color: var(--at-primary); font-size: 21px; padding-top: 3px; }
.workflow-list p { margin: 4px 0 0; }
.theme-choice { display: flex; gap: 12px; flex-wrap: wrap; border: 0; padding: 0; margin: 24px 0; }
.theme-choice legend { font-weight: 600; margin-bottom: 10px; }
.theme-choice label { display: flex; align-items: center; gap: 9px; padding: 12px; border: 1px solid var(--at-border); border-radius: 8px; cursor: pointer; }
.theme-choice .selected { border-color: var(--at-primary); background: var(--at-surface-muted); }
.welcome-small { font-size: 13px; }
.welcome-documents { display: flex; flex-wrap: wrap; gap: 4px; border-top: 1px solid var(--at-border); padding-top: 12px; }
.welcome-actions { display: flex; width: 100%; justify-content: space-between; gap: 12px; }
.welcome-actions > div { display: flex; gap: 8px; }
.storage-notice { position: fixed; z-index: 100; left: 16px; right: 16px; bottom: 16px; max-width: 1000px; margin-inline: auto; padding: 18px 22px; display: flex; align-items: center; gap: 24px; border: 1px solid var(--at-border); border-radius: 12px; background: var(--at-surface); color: var(--at-text); box-shadow: 0 8px 32px #0002; }
.storage-notice h2 { font-size: 16px; margin: 0 0 6px; }
.storage-notice p { font-size: 13px; line-height: 1.6; margin: 0; color: var(--at-text-muted); }
.notice-actions { display: flex; gap: 8px; flex-shrink: 0; }
.storage-error { margin: 12px 16px; }
.public-help { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px; padding: 12px 16px; }
@media (max-width: 540px) {
  .welcome-progress li { flex-direction: column; text-align: center; font-size: 11px; }
  .welcome-step { min-height: 0; }
  .welcome-actions { flex-wrap: wrap; }
  .storage-notice { align-items: stretch; flex-direction: column; gap: 12px; padding: 16px; }
  .notice-actions { justify-content: flex-end; }
}
</style>
