<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import AutoComplete from 'primevue/autocomplete'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
const props = withDefaults(defineProps<{ label: string; suggestions: readonly string[]; required?: boolean; disabled?: boolean; error?: string; hint?: string; type?: string; maxlength?: number; placeholder?: string; multiline?: boolean }>(), { maxlength: 300, type: 'text' })
const value = defineModel<string>({ required: true })
const emit = defineEmits<{ blur: [] }>()
const inputId = useId()
const matches = ref<string[]>([])
function search(event: { query: string }) {
  matches.value = props.suggestions.filter(text => text.toLocaleLowerCase().includes(event.query.toLocaleLowerCase())).slice(0, 15)
}
const priorNotes = computed(() => props.suggestions.map(text => ({ value: text, label: text.length > 90 ? text.slice(0, 90) + '…' : text })))
</script>
<template>
  <div class="suggestion-field">
    <label :for="inputId">{{ label }} <span v-if="required" class="required-note">(required)</span></label>
    <template v-if="multiline">
      <Textarea :id="inputId" v-model="value" class="at-form-control" rows="4" :maxlength="maxlength" :disabled="disabled" :invalid="Boolean(error)" :aria-describedby="error ? inputId + '-error' : undefined" @blur="emit('blur')" />
      <Select v-if="priorNotes.length" :model-value="null" :options="priorNotes" option-label="label" option-value="value" :aria-label="`Reuse previous ${label.toLowerCase()}`" placeholder="Reuse previous text…" :disabled="disabled" class="at-form-control" @update:model-value="value = $event" />
    </template>
    <AutoComplete v-else :input-id="inputId" v-model="value" :suggestions="matches" :dropdown="suggestions.length > 0" :min-length="1" :delay="100" :disabled="disabled" :invalid="Boolean(error)" :placeholder="placeholder" class="at-form-control" :input-props="{ type, maxlength, required, 'aria-describedby': error ? inputId + '-error' : hint ? inputId + '-hint' : undefined }" @complete="search" @blur="emit('blur')" />
    <small v-if="hint" :id="inputId + '-hint'">{{ hint }}</small>
    <small v-if="error" :id="inputId + '-error'" class="field-error" role="alert">{{ error }}</small>
  </div>
</template>
<style scoped>
.suggestion-field { min-width:0; }label { display:block; font-size:14px; font-weight:600; }.required-note, small { font-size:12px; font-weight:400; color:var(--at-text-muted); }small { display:block; line-height:1.5; margin-top:6px; }.field-error { color:var(--at-unsuccessful); }:deep(.p-autocomplete-input) { width:100%; min-width:0; }:deep(.p-autocomplete-option) { white-space:normal; overflow-wrap:anywhere; }
</style>
