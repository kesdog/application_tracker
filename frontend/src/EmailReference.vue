<script setup lang="ts">
import { computed } from 'vue'
import { emailReferences, emailReferenceUrl } from './emailReference'
const props = withDefaults(defineProps<{ reference: string | null; label?: string }>(), { label: 'email ref' })
const references = computed(() => emailReferences(props.reference).map(reference => ({ reference, url: emailReferenceUrl(reference) })))
</script>

<template>
  <span class="email-references"><template v-for="(item, index) in references" :key="item.reference">
    <a v-if="item.url" :href="item.url" :title="item.reference" target="_blank" rel="noopener noreferrer">{{ label }}{{ references.length > 1 ? ` ${index + 1}` : '' }}</a>
    <span v-else>{{ item.reference }}</span>
  </template></span>
</template>

<style scoped>
@layer legacy {
a { color:var(--at-link); text-underline-offset:3px; overflow-wrap:anywhere; }
.email-references { display:inline-flex; flex-wrap:wrap; gap:8px 14px; }
}
</style>
