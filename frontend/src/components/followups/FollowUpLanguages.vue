<script setup lang="ts">
import { computed, onUnmounted, ref, useId, watch } from 'vue'
import Button from 'primevue/button'
import { errorText, intlLocale, t } from '../../i18n'
import { emailLanguageCode } from '../../followupLanguages'
import { getFollowUpMessageVersions, restoreFollowUpMessageVersion, switchFollowUpLanguage, updateApplication, type Application, type FollowUp, type FollowUpMessageVersion } from '../../api'

const props = defineProps<{ application: Application; item: FollowUp; disabled?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const id = useId()
const selected = ref('en')
const applicationLanguage = ref('')
const versions = ref<FollowUpMessageVersion[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
let request = 0
const applicationLocked = computed(() => props.disabled || busy.value || props.application.status === 'CLOSED')
const locked = computed(() => applicationLocked.value || loading.value || props.item.content_available === false || props.item.status === 'SENT' || !!props.item.archived_at)
const languageName = (value: string) => value === 'en' ? t('English') : value === 'fr' ? t('French') : value
async function load() {
  const version = ++request
  selected.value = emailLanguageCode(props.item.message_language ?? String(props.item.template_snapshot.language ?? 'English'))
  versions.value = []; error.value = ''; loading.value = false
  if (props.item.content_available === false || props.item.channel === 'PHONE') return
  loading.value = true
  try {
    const result = await getFollowUpMessageVersions(props.application.id, props.item.id)
    if (version === request) { selected.value = result.current_language; versions.value = result.versions }
  } catch (reason) { if (version === request) error.value = reason instanceof Error ? reason.message : 'Unable to load saved message versions.' }
  finally { if (version === request) loading.value = false }
}
async function perform(action: () => Promise<unknown>, applicationOnly = false) {
  if (applicationOnly ? applicationLocked.value : locked.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action(); notice.value = applicationOnly ? 'Application email language saved. Existing messages keep their text.' : 'Message language saved. Previous versions are kept. Review before sending.'; emit('changed') }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Unable to change message language.' }
  finally { busy.value = false }
}
function useLanguage() { return perform(() => switchFollowUpLanguage(props.application.id, props.item.id, selected.value, props.item.revision)) }
function restore(version: FollowUpMessageVersion) { return perform(() => restoreFollowUpMessageVersion(props.application.id, props.item.id, version.id, props.item.revision)) }
async function saveApplicationLanguage() {
  await perform(() => updateApplication(props.application.id, {
    expected_revision: props.application.revision,
    followup_customization: { ...props.application.followup_customization, language: applicationLanguage.value === 'en' ? 'English' : applicationLanguage.value === 'fr' ? 'French' : applicationLanguage.value || null },
  }), true)
}
watch(() => [props.item.id, props.item.revision], load, { immediate: true })
watch(() => props.application.followup_customization?.language, value => { applicationLanguage.value = emailLanguageCode(value) }, { immediate: true })
onUnmounted(() => { request++ })
</script>

<template>
  <section v-if="item.channel !== 'PHONE'" class="message-languages" :aria-label="t('Follow-up email language')">
    <div class="language-controls"><label :for="id">{{ t('Email language') }}<select :id="id" v-model="selected" :disabled="locked"><option value="en">{{ t('English') }}</option><option value="fr">{{ t('French') }}</option><option v-if="!['en', 'fr'].includes(selected)" :value="selected">{{ languageName(selected) }}</option></select></label><Button type="button" severity="secondary" :disabled="locked || !['en', 'fr'].includes(selected)" @click="useLanguage">{{ t('Use this email language') }}</Button></div>
    <p class="hint">{{ t('Email language is independent of the app language. Reuse a saved version, or prepare a standard message in a new language. Other versions stay saved.') }}</p>
    <p v-if="disabled" class="hint">{{ t('Save your message edits before changing another setting.') }}</p>
    <p v-if="error" class="at-message error" role="alert">{{ errorText(error) }}</p><p v-if="notice" role="status">{{ t(notice) }}</p>
    <details><summary>{{ t('Email language for this application') }}</summary><label :for="id + '-application'">{{ t('Preferred email language for future follow-ups') }}<select :id="id + '-application'" v-model="applicationLanguage" :disabled="applicationLocked"><option value="">{{ t('Use the default email language') }}</option><option value="en">{{ t('English') }}</option><option value="fr">{{ t('French') }}</option><option v-if="applicationLanguage && !['en', 'fr'].includes(applicationLanguage)" :value="applicationLanguage">{{ applicationLanguage }}</option></select></label><p class="hint">{{ t('This preference applies only to this application. Existing message text keeps its language until you switch it above.') }}</p><Button type="button" severity="secondary" :disabled="applicationLocked" @click="saveApplicationLanguage">{{ t('Save application email language') }}</Button></details>
    <details><summary>{{ t('Saved message versions') }} ({{ versions.length }})</summary><p v-if="loading">{{ t('Loading saved message versions…') }}</p><p v-else-if="!versions.length">{{ t('No saved message versions yet.') }}</p><article v-for="version in versions" :key="version.id" class="saved-version"><div class="version-heading"><strong>{{ languageName(version.language) }}</strong><span v-if="version.active">{{ t('Current message') }}</span><time>{{ new Date(version.created_at).toLocaleString(intlLocale) }}</time></div><details><summary>{{ t('Preview saved message') }}</summary><strong>{{ version.subject }}</strong><pre>{{ version.body }}</pre></details><Button type="button" severity="secondary" :disabled="locked || version.active" @click="restore(version)">{{ t('Use saved version') }}</Button></article></details>
  </section>
</template>

<style scoped>
.message-languages{margin:16px 0;padding:16px;border:1px solid var(--at-border);border-radius:6px;background:var(--at-surface)}.language-controls,.version-heading{display:flex;gap:12px;flex-wrap:wrap;align-items:end}label{display:block;font-weight:600}select{display:block;max-width:100%;margin-top:6px;padding:10px;font:inherit;color:var(--at-text);background:var(--at-surface);border:1px solid var(--at-border);border-radius:5px}.hint,time{color:var(--at-text-muted);line-height:1.6}summary{cursor:pointer;margin:12px 0}.saved-version{padding:12px 0;border-top:1px solid var(--at-border)}.version-heading{align-items:center}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}@media(max-width:650px){.language-controls{align-items:stretch;flex-direction:column}.message-languages{padding:12px}}
</style>
