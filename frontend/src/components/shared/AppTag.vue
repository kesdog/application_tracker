<script setup lang="ts">
import { computed } from 'vue'
import Tag from 'primevue/tag'
import type { Tone } from '../../presentation/applicationPresentation'
import { appearanceVariable } from '../../settings/applyAppearance'

const props = withDefaults(defineProps<{ label: string; tone?: Tone; icon?: string }>(), { tone: 'neutral' })
const colors = computed(() => {
  const variable = appearanceVariable(props.tone === 'neutral' ? 'surfaceMuted' : props.tone)
  return {
    background: `var(${variable})`,
    color: `var(${variable}-contrast)`,
    border: `1px solid var(${variable})`,
  }
})
</script>
<template><Tag :value="label" :icon="icon" :style="colors" class="at-tag" /></template>
