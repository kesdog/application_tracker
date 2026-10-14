<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue'
import type { TemplateVariable } from '../../api'
const props = withDefaults(defineProps<{ modelValue: string; label: string; variables: TemplateVariable[]; rows?: number; disabled?: boolean }>(), { rows: 5, disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const textarea = ref<HTMLTextAreaElement | null>(null)
const mirror = ref<HTMLElement | null>(null)
const pickerOpen = ref(false)
const search = ref('')
const triggerStart = ref<number | null>(null)
const activeIndex = ref(0)
const listId = useId()
const matches = computed(() => props.variables.filter(v => `${v.key} ${v.label} ${v.group} ${v.aliases.join(' ')}`.toLowerCase().includes(search.value.toLowerCase())))
const parts = computed(() => props.modelValue.split(/(\{[^{}\n]+\})/g).map(text => ({ text, tag: /^\{[^{}\n]+\}$/.test(text) })))
function syncScroll() { if (mirror.value && textarea.value) { mirror.value.scrollTop = textarea.value.scrollTop; mirror.value.scrollLeft = textarea.value.scrollLeft } }
async function insert(key: string) {
  if (props.disabled) return
  const start = triggerStart.value ?? textarea.value?.selectionStart ?? props.modelValue.length
  const end = textarea.value?.selectionEnd ?? start
  const tag = `{${key}}`
  const current = textarea.value?.value ?? props.modelValue
  textarea.value?.focus()
  textarea.value?.setSelectionRange(start, end)
  // Native insertion preserves the browser's editing undo history where supported.
  if (typeof document.execCommand === 'function' && document.execCommand('insertText', false, tag)) {
    pickerOpen.value = false
    triggerStart.value = null
    return
  }
  emit('update:modelValue', current.slice(0, start) + tag + current.slice(end))
  pickerOpen.value = false
  triggerStart.value = null
  await nextTick()
  textarea.value?.focus(); textarea.value?.setSelectionRange(start + tag.length, start + tag.length)
}
function detectTrigger() {
  const input = textarea.value
  if (!input || props.disabled) return
  const before = input.value.slice(0, input.selectionStart)
  const match = before.match(/\{([^{}\n]*)$/)
  triggerStart.value = match ? input.selectionStart - match[0].length : null
  pickerOpen.value = !!match
  search.value = match?.[1] ?? ''
  activeIndex.value = 0
}
function input(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
  detectTrigger()
}
function openPicker() {
  triggerStart.value = null; search.value = ''; activeIndex.value = 0
  pickerOpen.value = !pickerOpen.value
}
function keyboard(event: KeyboardEvent) {
  if (!pickerOpen.value) return
  if (event.key === 'Escape') { event.preventDefault(); pickerOpen.value = false; triggerStart.value = null }
  else if (['ArrowDown', 'ArrowUp'].includes(event.key) && matches.value.length) {
    event.preventDefault()
    activeIndex.value = (activeIndex.value + (event.key === 'ArrowDown' ? 1 : -1) + matches.value.length) % matches.value.length
    void nextTick(() => document.getElementById(`${listId}-${activeIndex.value}`)?.scrollIntoView?.({ block: 'nearest' }))
  } else if (['Enter', 'Tab'].includes(event.key) && matches.value[activeIndex.value]) {
    event.preventDefault(); void insert(matches.value[activeIndex.value]!.key)
  }
}
</script>

<template>
  <div class="template-field">
    <div class="field-heading"><label><strong>{{ label }}</strong></label><button type="button" :disabled="disabled" :aria-expanded="pickerOpen" @click="openPicker">Insert variable</button></div>
    <div class="text-layer">
      <div ref="mirror" class="mirror" aria-hidden="true"><template v-for="(part, index) in parts" :key="index"><mark v-if="part.tag">{{ part.text }}</mark><span v-else>{{ part.text }}</span></template><span>{{ '\n' }}</span></div>
      <textarea ref="textarea" :aria-label="label" :value="modelValue" :rows="rows" :disabled="disabled" spellcheck="false" aria-autocomplete="list" :aria-controls="pickerOpen ? listId : undefined" :aria-activedescendant="pickerOpen && matches[activeIndex] ? `${listId}-${activeIndex}` : undefined" @scroll="syncScroll" @input="input" @click="detectTrigger" @keydown="keyboard" />
    </div>
    <div v-if="pickerOpen" class="picker"><input v-if="triggerStart === null" v-model="search" type="search" aria-label="Find a template variable" placeholder="Search application fields…" @input="activeIndex = 0" /><div :id="listId" class="variable-list" role="listbox" :aria-label="`${label} variables`"><button v-for="(variable, index) in matches" :id="`${listId}-${index}`" :key="variable.key" type="button" role="option" :aria-selected="activeIndex === index" :class="{ selected: activeIndex === index }" @mousedown.prevent @click="insert(variable.key)"><span>{{ variable.label }} <small>{{ variable.group }}</small></span><code>{{ '{' + variable.key + '}' }}</code></button></div><p v-if="!matches.length">No matching fields.</p></div>
  </div>
</template>

<style scoped>
.template-field{margin:16px 0}.field-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}.text-layer{position:relative;border:1px solid var(--at-border);border-radius:6px;background:var(--at-surface)}textarea,.mirror{box-sizing:border-box;width:100%;padding:12px;font:14px/1.65 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow-wrap:break-word;tab-size:4;border:0;margin:0}textarea{position:relative;display:block;background:transparent;color:transparent;caret-color:var(--at-text);resize:vertical;min-height:48px}.mirror{position:absolute;inset:0;overflow:hidden;pointer-events:none;color:var(--at-text)}mark{background:color-mix(in srgb,var(--at-primary) 18%,var(--at-surface));color:var(--at-primary);border-radius:3px}button,input{font:inherit;padding:8px 10px;border:1px solid var(--at-border);border-radius:5px;background:var(--at-surface);color:var(--at-text)}button{cursor:pointer}input{width:100%;margin:10px 0}.picker{border:1px solid var(--at-border);padding:8px;border-radius:6px}.variable-list{max-height:250px;overflow:auto;display:grid;gap:5px}.variable-list button{display:flex;justify-content:space-between;gap:12px;text-align:left}.variable-list small{display:block;color:var(--at-text-muted)}.variable-list button.selected{background:var(--at-surface-muted);border-color:var(--at-primary)}code{font-size:12px;overflow-wrap:anywhere}
@media(max-width:650px){.variable-list button{flex-wrap:wrap}.field-heading{align-items:flex-start}}
</style>
