<script setup lang="ts">
import { t, messageText, errorText } from '../../i18n'

import { onMounted, ref, useId } from 'vue'
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import { getGeneralSettings, saveGeneralSettings } from '../../api'

const id = useId()
const limit = ref<number | null>(100)
const notBefore = ref('2026-01-01')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const notice = ref('')
async function load() {
  loading.value = true; error.value = ''
  try { const settings = await getGeneralSettings(); limit.value = settings.mail_sync_max_messages; notBefore.value = settings.mail_sync_not_before ?? '2026-01-01' }
  catch { error.value = t("Could not load the mail scan limit. Try again.") }
  finally { loading.value = false }
}
async function save() {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(notBefore.value) || notBefore.value < '2026-01-01') {
    error.value = t('Choose an application date on or after 2026-01-01.'); return
  }
  if (limit.value === null || !Number.isInteger(limit.value) || limit.value < 1 || limit.value > 1000) {
    error.value = t("Choose a whole number from 1 to 1,000."); notice.value = ''; return
  }
  saving.value = true; error.value = ''; notice.value = ''
  try {
    // Read the latest unrelated preferences before saving this one value.
    // The existing revision guard still catches a simultaneous settings edit.
    const current = await getGeneralSettings()
    const saved = await saveGeneralSettings({ ...current, mail_sync_max_messages: limit.value, mail_sync_not_before: notBefore.value })
    limit.value = saved.mail_sync_max_messages
    notice.value = t("Mail scan limit saved. It applies to the next sync.")
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("Could not save the mail scan limit.") }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <section class="mail-sync-settings" :aria-labelledby="`${id}-heading`">
    <h3 :id="`${id}-heading`">{{ t("Mail scan & updates") }}</h3>
    <p>{{ t("Choose how much new mail to check when you sync applications.") }}</p>
    <p v-if="loading" role="status">{{ t("Loading mail scan settings…") }}</p>
    <form v-else @submit.prevent="save">
      <label :for="`${id}-boundary`">{{ t('Earliest application date') }}</label>
      <input :id="`${id}-boundary`" v-model="notBefore" type="date" min="2026-01-01" required :disabled="saving" />
      <p>{{ t('Older applications are excluded even when they are mentioned in recent mail. This boundary also applies to existing Gmail connections.') }}</p>
      <label :for="`${id}-limit`">{{ t("Maximum new emails per sync") }}</label>
      <InputNumber v-model="limit" :input-id="`${id}-limit`" :min="1" :max="1000" :max-fraction-digits="0" :use-grouping="false" :disabled="saving" :pt="{ pcInputText: { root: { 'aria-describedby': `${id}-help` } } }" />
      <p :id="`${id}-help`">{{ t("Default: 100. Choose 1–1,000. Each new email uses one place, including emails that need review. Previously checked emails do not count again. Each email can add or update at most one application. This limit applies to Gmail; device sync still runs separately.") }}</p>
      <p>{{ t("When the limit is reached, saved changes are kept. Use Continue sync to check more mail. Nothing is sent.") }}</p>
      <Button type="submit" :disabled="saving">{{ saving ? t("Saving…") : t("Save mail scan settings") }}</Button>
      <Button v-if="error" type="button" severity="secondary" :disabled="saving" @click="load">{{ t("Reload mail scan limit") }}</Button>
    </form>
    <p v-if="error" role="alert">{{ errorText(String((error) ?? '')) }}</p>
    <p v-if="notice" role="status">{{ messageText(String((notice) ?? '')) }}</p>
  </section>
</template>

<style scoped>
.mail-sync-settings { padding:24px; margin:20px 0; border:1px solid var(--at-border); border-radius:8px; background:var(--at-surface); }
p { color:var(--at-text-muted); line-height:1.5; }label { display:block; font-weight:600; margin:12px 0 8px; }button { margin:8px 8px 0 0; }
@media(max-width:650px) { .mail-sync-settings { padding:16px; } }
</style>
