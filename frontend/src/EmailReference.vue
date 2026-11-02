<script setup lang="ts">
import { t, messageText } from './i18n'

import { computed } from 'vue'
import { emailReferences, emailReferenceUrl, primaryEmailReference } from './emailReference'
const props = withDefaults(defineProps<{ reference: string | null; label?: string; primary?: boolean; context?: string }>(), { get label() { return t("Open email") } })
const references = computed(() => {
  const selected = props.primary ? emailReferences(primaryEmailReference(props.reference)) : emailReferences(props.reference)
  return selected.map(reference => {
    const url = emailReferenceUrl(reference)
    const search = url && new URL(url).hostname === 'mail.google.com' && new URL(url).hash.startsWith('#search/')
    return { reference, url, label: search ? t("Find email") : props.label }
  })
})
function linkLabel(label: string, index: number) {
  return label + (references.value.length > 1 ? ` ${index + 1}` : '')
}
</script>

<template>
  <span class="email-references"><template v-for="(item, index) in references" :key="item.reference">
    <a v-if="item.url" :href="item.url" :title="t('{p0} (opens in a new tab)', { p0: linkLabel(item.label, index) })" :aria-label="t('{p0}{p1} (opens in a new tab)', { p0: linkLabel(item.label, index), p1: context ? ` for ${context}` : '' })" target="_blank" rel="noopener noreferrer"><span>{{ messageText(String((linkLabel(item.label, index)) ?? '')) }}</span><i class="pi pi-external-link" aria-hidden="true" /></a>
    <span v-else>{{ item.reference }}</span>
  </template></span>
</template>

<style scoped>
@layer legacy {
a { display:inline-flex; align-items:center; gap:6px; min-height:44px; padding:4px 0; border-radius:4px; color:var(--at-link); text-underline-offset:3px; white-space:nowrap; }
a:focus-visible { outline:3px solid var(--at-focus); outline-offset:3px; }
i { font-size:11px; }
.email-references { display:inline-flex; flex-wrap:wrap; gap:8px 14px; max-width:100%; min-width:0; }
}
</style>
