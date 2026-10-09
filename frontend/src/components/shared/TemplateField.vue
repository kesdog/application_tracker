<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { TemplateVariable } from '../../api'
const props = withDefaults(defineProps<{ modelValue: string; label: string; variables: TemplateVariable[]; rows?: number; disabled?: boolean }>(), { rows: 5, disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const textarea = ref<HTMLTextAreaElement | null>(null)
const mirror = ref<HTMLElement | null>(null)
const pickerOpen = ref(false)
const search = ref('')
const matches = computed(() => props.variables.filter(v => `${v.key} ${v.label} ${v.group}`.toLowerCase().includes(search.value.toLowerCase())))
const parts = computed(() => props.modelValue.split(/(\{[^{}\n]+\})/g).map(text => ({ text, tag: /^\{[^{}\n]+\}$/.test(text) })))
function syncScroll() { if (mirror.value && textarea.value) { mirror.value.scrollTop = textarea.value.scrollTop; mirror.value.scrollLeft = textarea.value.scrollLeft } }
async function insert(key: string) {
  const start = textarea.value?.selectionStart ?? props.modelValue.length
  const end = textarea.value?.selectionEnd ?? start
  const tag = `{${key}}`
  textarea.value?.focus()
  textarea.value?.setSelectionRange(start, end)
  // Native insertion preserves the browser's editing undo history where supported.
  if (typeof document.execCommand === 'function' && document.execCommand('insertText', false, tag)) {
    pickerOpen.value = false
    return
  }
  emit('update:modelValue', props.modelValue.slice(0, start) + tag + props.modelValue.slice(end))
  pickerOpen.value = false
  await nextTick()
  textarea.value?.focus(); textarea.value?.setSelectionRange(start + tag.length, start + tag.length)
}
</script>

<template>
  <div class="template-field">
    <div class="field-heading"><label><strong>{{ label }}</strong></label><button type="button" :disabled="disabled" :aria-expanded="pickerOpen" @click="pickerOpen = !pickerOpen">Insert variable</button></div>
    <div class="text-layer">
      <div ref="mirror" class="mirror" aria-hidden="true"><template v-for="(part, index) in parts" :key="index"><mark v-if="part.tag">{{ part.text }}</mark><span v-else>{{ part.text }}</span></template><span>{{ '\n' }}</span></div>
      <textarea ref="textarea" :aria-label="label" :value="modelValue" :rows="rows" :disabled="disabled" spellcheck="false" @scroll="syncScroll" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" />
    </div>
    <div v-if="pickerOpen" class="picker"><input v-model="search" type="search" aria-label="Find a template variable" placeholder="Search application fields…" /><div class="variable-list"><button v-for="variable in matches" :key="variable.key" type="button" @click="insert(variable.key)"><span>{{ variable.label }} <small>{{ variable.group }}</small></span><code>{{ '{' + variable.key + '}' }}</code></button></div><p v-if="!matches.length">No matching fields.</p></div>
  </div>
</template>

<style scoped>
.template-field{margin:16px 0}.field-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}.text-layer{position:relative;border:1px solid var(--at-border);border-radius:6px;background:var(--at-surface)}textarea,.mirror{box-sizing:border-box;width:100%;padding:12px;font:14px/1.65 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow-wrap:break-word;tab-size:4;border:0;margin:0}textarea{position:relative;display:block;background:transparent;color:transparent;caret-color:var(--at-text);resize:vertical;min-height:48px}.mirror{position:absolute;inset:0;overflow:hidden;pointer-events:none;color:var(--at-text)}mark{background:color-mix(in srgb,var(--at-primary) 18%,var(--at-surface));color:var(--at-primary);border-radius:3px}button,input{font:inherit;padding:8px 10px;border:1px solid var(--at-border);border-radius:5px;background:var(--at-surface);color:var(--at-text)}button{cursor:pointer}input{width:100%;margin:10px 0}.picker{border:1px solid var(--at-border);padding:8px;border-radius:6px}.variable-list{max-height:250px;overflow:auto;display:grid;gap:5px}.variable-list button{display:flex;justify-content:space-between;gap:12px;text-align:left}.variable-list small{display:block;color:var(--at-text-muted)}code{font-size:12px;overflow-wrap:anywhere}
@media(max-width:650px){.variable-list button{flex-wrap:wrap}.field-heading{align-items:flex-start}}
</style>
