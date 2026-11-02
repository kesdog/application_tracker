<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import TemplateField from '../shared/TemplateField.vue'
import RecipientPageReports from '../followups/RecipientPageReports.vue'
import { getGeneralSettings, saveGeneralSettings, getTemplateVariables, previewTemplate, listApplications, type GeneralSettings, type TemplateVariable, type TemplatePreview, type Application } from '../../api'
const settings = ref<GeneralSettings | null>(null)
const variables = ref<TemplateVariable[]>([])
const applications = ref<Application[]>([])
const selected = ref('')
const preview = ref<TemplatePreview | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
let previewVersion = 0
let previewTimer: ReturnType<typeof setTimeout> | undefined
const unresolved = computed(() => [...new Set([...(preview.value?.subject.missing ?? []), ...(preview.value?.body.missing ?? []), ...(preview.value?.subject.unknown ?? []), ...(preview.value?.body.unknown ?? [])])])
async function load() {
  busy.value = true; error.value = ''
  try { [settings.value, variables.value, applications.value] = await Promise.all([getGeneralSettings(), getTemplateVariables(), listApplications()]); await showPreview() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to load general settings.") }
  finally { busy.value = false }
}
async function showPreview() {
  if (!settings.value) return
  const version = ++previewVersion
  try { const result = await previewTemplate({ subject: settings.value.subject_template, body: settings.value.body_template, ...(selected.value ? { application_id: selected.value } : {}), customization: { signature: settings.value.signature, language: settings.value.language, tone: settings.value.tone } }); if (version === previewVersion) preview.value = result }
  catch (reason) { if (version === previewVersion) error.value = reason instanceof Error ? reason.message : t("Unable to preview.") }
}
async function save() {
  if (!settings.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { settings.value = await saveGeneralSettings(settings.value); notice.value = t("General settings saved. Existing messages keep their saved text."); await showPreview() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t("Unable to save settings.") }
  finally { busy.value = false }
}
onMounted(() => { void load(); window.addEventListener('tracker:language-templates-changed', load) })
watch(() => [settings.value?.subject_template, settings.value?.body_template, settings.value?.signature, settings.value?.language, settings.value?.tone, selected.value], () => {
  clearTimeout(previewTimer)
  previewVersion++
  previewTimer = setTimeout(() => void showPreview(), 250)
})
onUnmounted(() => { clearTimeout(previewTimer); previewVersion++; window.removeEventListener('tracker:language-templates-changed', load) })
</script>

<template>
  <section class="panel" aria-labelledby="general-settings-heading"><h3 id="general-settings-heading">{{ t("Default follow-up message") }}</h3><p>{{ t("Prepare a message as soon as an application is added. Edit the default below, then customize any job separately.") }}</p>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(String((error) ?? '')) }}</p><p v-if="notice" class="at-message success" role="status">{{ messageText(String((notice) ?? '')) }}</p><p v-if="!settings">{{ t("Loading general settings…") }}</p>
    <form v-if="settings" @submit.prevent="save"><fieldset :disabled="busy"><legend class="sr-only">{{ t("Follow-up defaults") }}</legend>
      <TemplateField v-model="settings.subject_template" :label="t('Default subject template')" :variables="variables" :rows="2" :disabled="busy" />
      <TemplateField v-model="settings.body_template" :label="t('Default message template')" :variables="variables" :rows="9" :disabled="busy" />
      <details><summary>{{ t("Language, signature & instructions") }}</summary>      <div class="grid"><label>{{ t("Signature") }}<textarea v-model="settings.signature" rows="3" maxlength="3000" /></label><div><label>{{ t("Language") }}<input v-model="settings.language" maxlength="80" /></label><label>{{ t("Tone") }}<input v-model="settings.tone" maxlength="120" /></label></div></div>
      <label>{{ t("Default instructions for you or your AI agent") }}<textarea v-model="settings.instructions" rows="3" maxlength="12000" :placeholder="t('For example: keep messages brief and don\'t mention salary.')" /></label><p class="hint">{{ t("Instructions are guidance for manual editing; AI routes receive the same settings.") }}</p>
</details>
      <details><summary>{{ t("Schedule & reminder rules") }}</summary>      <div class="grid"><label>{{ t("Delay after application or confirmed send (calendar days)") }}<input v-model.number="settings.followup_delay_days" type="number" min="0" max="3650" required /></label><label>{{ t("Automatic follow-up limit") }}<input v-model.number="settings.max_followup_suggestions" type="number" min="0" max="100" required /></label><label>{{ t("Timezone") }}<input v-model="settings.timezone" required :placeholder="t('Europe/Paris')" /></label><label>{{ t("Reminder time") }}<input v-model="settings.reminder_time" type="time" required /></label></div>
      <div class="reminder-preferences"><label class="check"><input v-model="settings.notifications_enabled" type="checkbox" /> {{ t("Enable scheduled notices") }}</label><label class="check"><input v-model="settings.daily_digest" type="checkbox" /> {{ t("One daily phone digest at or after the reminder time") }}</label><p class="hint">{{ t("With digest off, newly due reminders are grouped on each scan. Quiet hours defer reminders. Phone delivery requires an enabled device.") }}</p><div class="grid"><label>{{ t("Quiet hours start") }}<input v-model="settings.quiet_start" type="time" required /></label><label>{{ t("Quiet hours end") }}<input v-model="settings.quiet_end" type="time" required /></label></div></div>
      <label>{{ t("Review as possibly unsuccessful after this many unanswered follow-ups") }}<input v-model.number="settings.unsuccessful_review_after" type="number" min="0" max="100" required /></label><p class="hint">{{ t("Default: 3. Counts actual sends or completed calls since the last recorded employer reply. The application stays open for your review. Set 0 to disable. This is separate from the automatic follow-up limit; add another follow-up manually or raise that limit if needed.") }}</p>
</details>
      <details><summary>{{ t("Recipient research limit") }}</summary>      <label>{{ t("Recipient research: new pages per application run") }}<input v-model.number="settings.recipient_page_limit" type="number" min="1" max="100" required /></label><p class="hint">{{ t("Default: 6. Saved page reports are reused without spending this limit. Override it on an application's recipient panel. A run also has a time limit, so it may fetch fewer pages.") }}</p>
</details>
      <div class="actions"><Button type="submit" :disabled="busy">{{ t("Save general settings") }}</Button><Button type="button" severity="secondary" :disabled="busy" @click="showPreview">{{ t("Update preview") }}</Button></div>
      <details><summary>{{ t("Message preview") }}</summary><div class="preview"><div class="actions"><label>{{ t("Preview with") }}<select v-model="selected" @change="showPreview"><option value="">{{ t("Sample application") }}</option><option v-for="app in applications" :key="app.id" :value="app.id">{{ app.company }} · {{ app.job_title }}</option></select></label></div><template v-if="preview"><strong>{{ preview.subject.text }}</strong><pre>{{ preview.body.text }}</pre><p v-if="unresolved.length" class="at-message warning">{{ t("Fill or remove these variables on the individual message before marking ready:") }} {{ unresolved.map(v => '{' + v + '}').join(', ') }}</p></template></div>
      </details>
    </fieldset></form>
    <details><summary>{{ t("Saved recipient research") }}</summary><RecipientPageReports /></details>
  </section>
</template>

<style scoped>
.panel{border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface);padding:24px;margin:20px 0}.panel>p,.hint{color:var(--at-text-muted)}fieldset{border:0;padding:0;margin:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}label{display:block;margin:12px 0;font-weight:600}input,textarea,select{display:block;width:100%;box-sizing:border-box;margin-top:6px;padding:10px;font:inherit;color:var(--at-text);background:var(--at-surface);border:1px solid var(--at-border);border-radius:5px}.check{display:flex;align-items:center;gap:10px}.check input{width:auto;margin:0}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.preview{background:var(--at-background);border:1px solid var(--at-border);padding:16px;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}summary{cursor:pointer;margin:14px 0}@media(max-width:650px){.grid{grid-template-columns:1fr}.panel{padding:16px}}
</style>
