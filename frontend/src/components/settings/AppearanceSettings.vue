<script setup lang="ts">
import { computed, reactive } from 'vue'
import Button from 'primevue/button'
import ColorPicker from 'primevue/colorpicker'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import { appearance, appearanceSaveError, applyAppearancePreset, resetAppearance, updateAppearance } from '../../settings/appearanceStore'
import { appearancePresets } from '../../settings/appearancePresets'
import { appearanceColors, type AppearanceColor } from '../../settings/appearanceDefaults'
import { contrastRatio } from '../../settings/colorContrast'

const labels: Record<AppearanceColor, string> = {
  primary: 'Primary', primaryHover: 'Primary hover', link: 'Links', focus: 'Focus ring',
  background: 'Background', surface: 'Surface', surfaceMuted: 'Muted surface', border: 'Border',
  text: 'Text', textMuted: 'Muted text', submitted: 'Submitted', interview: 'Interview',
  successful: 'Successful', unsuccessful: 'Unsuccessful', withdrawn: 'Withdrawn', cancelled: 'Job cancelled',
  ghosted: 'Ghosted', overdue: 'Overdue', dueSoon: 'Due soon', live: 'Live posting', postingClosed: 'Closed posting',
}
const drafts = reactive<Partial<Record<AppearanceColor, string>>>({})
const invalid = reactive<Partial<Record<AppearanceColor, boolean>>>({})
const currentPreset = computed(() => appearancePresets.find(preset => appearanceColors.every(key => preset.colors[key] === appearance[key]))?.id ?? null)
const warnings = computed(() => [
  ['Text on background', appearance.text, appearance.background],
  ['Text on surface', appearance.text, appearance.surface],
  ['Muted text on surface', appearance.textMuted, appearance.surface],
  ['Text on muted surface', appearance.text, appearance.surfaceMuted],
  ['Links on surface', appearance.link, appearance.surface],
].map(([label, foreground, background]) => ({ label, ratio: contrastRatio(foreground!, background!) })).filter(pair => pair.ratio < 4.5))

function setHex(key: AppearanceColor, value: string) {
  drafts[key] = value
  invalid[key] = !updateAppearance(key, value)
}
function setPicker(key: AppearanceColor, value: unknown) {
  if (typeof value === 'string') {
    setHex(key, '#' + value.replace(/^#/, ''))
    if (!invalid[key]) delete drafts[key]
  }
}
function reset() {
  resetAppearance()
  clearDrafts()
}
function clearDrafts() {
  for (const key of appearanceColors) { delete drafts[key]; delete invalid[key] }
}
function selectPreset(id: string) {
  if (applyAppearancePreset(id)) clearDrafts()
}
</script>

<template>
  <section class="appearance-panel" aria-labelledby="appearance-title">
    <div class="appearance-heading"><div><h3 id="appearance-title">Appearance</h3><p>Changes preview immediately and are saved in this browser.</p></div><Button label="Reset appearance" severity="secondary" outlined @click="reset" /></div>
    <div class="preset-field"><label for="appearance-preset">Theme preset</label><Select input-id="appearance-preset" :model-value="currentPreset" :options="appearancePresets" option-label="label" option-value="id" placeholder="Custom colors" @update:model-value="selectPreset" /><p>Start with a preset, then adjust any color below.</p></div>
    <div class="appearance-preview" aria-label="Appearance preview"><strong>Your workspace</strong><span>Text and surface preview</span><a href="#/applications">View applications</a></div>
    <div v-if="warnings.length" class="at-message warning" role="status"><strong>Some colors may be difficult to read.</strong><ul><li v-for="pair in warnings" :key="pair.label">{{ pair.label }}: {{ pair.ratio.toFixed(2) }}:1 contrast (4.5:1 recommended).</li></ul></div>
    <p v-if="appearanceSaveError" class="at-message warning" role="status">{{ appearanceSaveError }}</p>
    <div class="color-grid">
      <div v-for="key in appearanceColors" :key="key" class="color-field">
        <label :for="`appearance-${key}`">{{ labels[key] }}</label>
        <div class="color-controls"><ColorPicker :model-value="appearance[key].slice(1)" format="hex" :pt="{ preview: { 'aria-label': `${labels[key]} color picker` } }" @update:model-value="setPicker(key, $event)" /><InputText :id="`appearance-${key}`" :model-value="drafts[key] ?? appearance[key]" :invalid="invalid[key]" :aria-describedby="invalid[key] ? `appearance-error-${key}` : undefined" spellcheck="false" maxlength="7" @update:model-value="setHex(key, $event ?? '')" @blur="!invalid[key] && delete drafts[key]" /></div>
        <small v-if="invalid[key]" :id="`appearance-error-${key}`" class="error">Enter a hex color such as #263e5c.</small>
      </div>
    </div>
  </section>
</template>

<style scoped>
.appearance-panel { background:var(--at-surface); border:1px solid var(--at-border); border-radius:8px; padding:24px; margin:20px 0; }
.appearance-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; }
.preset-field { margin-top:16px; }.preset-field label { display:block; font-size:13px; font-weight:600; margin-bottom:7px; }.preset-field :deep(.p-select) { width:220px; max-width:100%; }
p { color:var(--at-text-muted); font-size:14px; }
.appearance-preview { display:flex; flex-wrap:wrap; gap:16px; align-items:center; padding:16px; margin:16px 0; background:var(--at-background); border:1px solid var(--at-border); border-radius:6px; }
.appearance-preview span { color:var(--at-text-muted); }
.color-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:18px; margin-top:24px; }
.color-field label { display:block; font-size:13px; font-weight:600; margin-bottom:7px; }
.color-controls { display:flex; align-items:center; gap:10px; }.color-controls input { width:120px; font-family:monospace; }
.color-field small { display:block; margin:6px 0 0; }
</style>
