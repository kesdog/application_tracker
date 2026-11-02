<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import { locale, languages, languageSaveError, setLocale, t, errorText } from '../../i18n'
import { getGeneralSettings, changeFollowUpLanguage } from '../../api'
import { emailLanguageCode } from '../../followupLanguages'

const rewrite = ref(false)
const busy = ref(false)
const error = ref('')
const rewritten = ref<number | null>(null)
const appliedLanguage = ref('')
const emailLanguage = ref('en')
onMounted(async () => {
  try { emailLanguage.value = emailLanguageCode((await getGeneralSettings()).language) || 'en' }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to load general settings.' }
})
function select(event: Event) {
  setLocale((event.target as HTMLSelectElement).value)
  rewritten.value = null
}
async function applyToEmails() {
  if (busy.value) return
  const target = emailLanguage.value as 'en' | 'fr'
  const rewriteExisting = rewrite.value
  busy.value = true; error.value = ''; rewritten.value = null
  try {
    const settings = await getGeneralSettings()
    const result = await changeFollowUpLanguage(target, rewriteExisting, settings.revision)
    rewritten.value = result.rewritten
    appliedLanguage.value = target === 'fr' ? t('French') : t('English')
    window.dispatchEvent(new CustomEvent('tracker:language-templates-changed'))
    window.dispatchEvent(new CustomEvent('tracker:invalidate', { detail: { topic: 'followup.updated' } }))
  } catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to update follow-up language.' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="language-panel" aria-labelledby="language-heading">
    <h3 id="language-heading">{{ t('Language') }}</h3>
    <label for="interface-language">{{ t('App language') }}</label>
    <select id="interface-language" :value="locale" :disabled="busy" @change="select"><option v-for="language in languages" :key="language.value" :value="language.value" :lang="language.value">{{ language.label }}</option></select>
    <p>{{ t('Changes apply immediately and are saved in this browser. Your application data stays in its original language.') }}</p>
    <p v-if="languageSaveError" class="at-message warning" role="status">{{ errorText(languageSaveError) }}</p>
    <details>
      <summary>{{ t('Default email language') }}</summary>
      <p>{{ t('The app language only changes the interface. Each application and follow-up can use a different email language.') }}</p>
      <label for="default-email-language">{{ t('Default email language') }}</label><select id="default-email-language" v-model="emailLanguage" :disabled="busy"><option value="en">{{ t('English') }}</option><option value="fr">{{ t('French') }}</option><option v-if="!['en', 'fr'].includes(emailLanguage)" :value="emailLanguage">{{ emailLanguage }}</option></select>
      <p>{{ t('Choose the standard template for future follow-ups. Application and message language preferences take priority.') }}</p>
      <label class="check"><input v-model="rewrite" type="checkbox" :disabled="busy" />{{ t('Also update pending emails that use the default language') }}</label>
      <p v-if="rewrite" class="at-message warning">{{ t('Previous language versions are kept and can be restored from each follow-up. Applications and messages with their own language preference are skipped. Updated messages return to Prepared for review.') }}</p>
      <Button type="button" :disabled="busy || !['en', 'fr'].includes(emailLanguage)" @click="applyToEmails">{{ busy ? t('Saving…') : t('Save default email language') }}</Button>
    </details>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(error) }}</p>
    <p v-if="rewritten !== null" class="at-message success" role="status">{{ t('Follow-up defaults are now in {p0}. {p1} pending emails rewritten for review.', { p0: appliedLanguage, p1: rewritten }) }}</p>
  </section>
</template>

<style scoped>
.language-panel{padding:24px;margin:20px 0;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}label{display:block;font-weight:600;margin-block:12px}select{font:inherit;color:var(--at-text);background:var(--at-surface);padding:10px;border:1px solid var(--at-border);border-radius:5px;max-width:100%;min-width:180px}p{color:var(--at-text-muted);line-height:1.6}.check{display:flex;align-items:flex-start;gap:10px}.check input{margin-top:4px;flex-shrink:0}summary{cursor:pointer;margin-top:18px}@media(max-width:650px){.language-panel{padding:16px}}
</style>
