<script setup lang="ts">
import { computed, useId } from 'vue'
import PrimeDatePicker from 'primevue/datepicker'
const props = defineProps<{ label: string; min?: string; max?: string; required?: boolean; disabled?: boolean }>()
const value = defineModel<string | null>()
const inputId = useId()
const parse = (date: string | undefined | null) => date ? new Date(`${date}T12:00:00`) : undefined
const date = computed({
  get: () => parse(value.value) ?? null,
  set: (selected: Date | null) => {
    value.value = selected ? `${selected.getFullYear()}-${String(selected.getMonth() + 1).padStart(2, '0')}-${String(selected.getDate()).padStart(2, '0')}` : ''
  },
})
</script>
<template><div class="date-field"><label :for="inputId">{{ label }}</label><PrimeDatePicker :input-id="inputId" v-model="date" date-format="yy-mm-dd" show-icon show-button-bar :min-date="parse(min)" :max-date="parse(max)" :required="required" :disabled="disabled" :manual-input="false" class="at-form-control" /></div></template>
<style scoped>
@layer legacy {
.date-field { min-width:0; }label { display:block; font-size:13px; font-weight:600; }
}
</style>
