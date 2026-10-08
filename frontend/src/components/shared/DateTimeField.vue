<script setup lang="ts">
import { computed, useId } from 'vue'
import DatePicker from 'primevue/datepicker'
const props = defineProps<{ label: string; required?: boolean; disabled?: boolean }>()
const value = defineModel<string>()
const inputId = useId()
const date = computed({
  get: () => value.value ? new Date(value.value) : null,
  set: (selected: Date | null) => {
    value.value = selected ? `${selected.getFullYear()}-${String(selected.getMonth() + 1).padStart(2, '0')}-${String(selected.getDate()).padStart(2, '0')}T${String(selected.getHours()).padStart(2, '0')}:${String(selected.getMinutes()).padStart(2, '0')}` : ''
  },
})
</script>
<template><div class="datetime-field"><label :for="inputId">{{ label }}</label><DatePicker :input-id="inputId" v-model="date" date-format="yy-mm-dd" show-time hour-format="24" show-icon show-button-bar :required="required" :disabled="disabled" :manual-input="false" class="at-form-control" /></div></template>
<style scoped>.datetime-field { min-width:0; margin:12px 0; }label { display:block; font-size:13px; font-weight:600; }</style>
