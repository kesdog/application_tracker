<script setup lang="ts">
import { computed, useId } from 'vue'
import InputNumber from 'primevue/inputnumber'
defineProps<{ label: string; min?: number; max?: number; placeholder?: string; disabled?: boolean }>()
const value = defineModel<number | null | ''>()
const inputId = useId()
const number = computed({ get: () => typeof value.value === 'number' ? value.value : null, set: (number: number | null) => { value.value = number } })
</script>
<template><div class="number-field"><label :for="inputId">{{ label }}</label><InputNumber :input-id="inputId" v-model="number" :min="min" :max="max" :placeholder="placeholder" :disabled="disabled" :use-grouping="false" :max-fraction-digits="0" class="at-form-control" /></div></template>
<style scoped>.number-field { min-width:0; }label { display:block; font-size:13px; font-weight:600; }</style>
