<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
const props = defineProps<{ label: string; min?: string; max?: string }>()
const value = defineModel<string>()
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const open = ref(false)
const month = ref(new Date().getMonth())
const year = ref(new Date().getFullYear())
const calendarYear = computed(() => Number.isFinite(year.value) ? Math.max(1900, Math.min(9999, year.value)) : new Date().getFullYear())
const months = Array.from({ length: 12 }, (_, index) => new Date(2026, index, 1).toLocaleString(undefined, { month: 'long' }))
function dateValue(day: Date) { return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}` }
const today = dateValue(new Date())
function allowed(day: string) { return (!props.min || day >= props.min) && (!props.max || day <= props.max) }
const days = computed(() => {
  const first = new Date(calendarYear.value, month.value, 1)
  const offset = (first.getDay() + 6) % 7
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(calendarYear.value, month.value, index - offset + 1)
    return { value: dateValue(date), number: date.getDate(), current: date.getMonth() === month.value, label: date.toLocaleDateString(undefined, { dateStyle: 'full' }) }
  })
})
function toggleCalendar() {
  if (!open.value) {
    const selected = value.value ? new Date(`${value.value}T12:00:00`) : new Date()
    month.value = selected.getMonth(); year.value = selected.getFullYear()
  }
  open.value = !open.value
}
function changeMonth(offset: number) {
  const date = new Date(calendarYear.value, month.value + offset, 1)
  month.value = date.getMonth(); year.value = date.getFullYear()
}
function choose(day: string) { value.value = day; close() }
function close() { open.value = false; trigger.value?.focus() }
function clickOutside(event: MouseEvent) { if (!root.value?.contains(event.target as Node)) open.value = false }
onMounted(() => document.addEventListener('click', clickOutside))
onUnmounted(() => document.removeEventListener('click', clickOutside))
</script>

<template>
  <div ref="root" class="date-field" @keydown.esc.stop="close">
    <label>{{ label }}<input v-model="value" type="date" :min="min" :max="max" /></label>
    <button ref="trigger" class="calendar-trigger" type="button" :aria-label="`Open calendar for ${label.toLowerCase()}`" :aria-expanded="open" @click="toggleCalendar"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 3v4m10-4v4M4 10h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" /></svg></button>
    <div v-if="open" class="calendar" role="dialog" :aria-label="`${label} calendar`">
      <div class="calendar-heading"><button type="button" aria-label="Previous month" @click="changeMonth(-1)">‹</button><select v-model="month" aria-label="Calendar month"><option v-for="(name, index) in months" :key="index" :value="index">{{ name }}</option></select><input v-model.number="year" type="number" min="1900" max="9999" aria-label="Calendar year" /><button type="button" aria-label="Next month" @click="changeMonth(1)">›</button></div>
      <div class="days"><span v-for="day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']" :key="day" class="weekday">{{ day }}</span><button v-for="day in days" :key="day.value" type="button" :aria-label="day.label" :aria-pressed="day.value === value" :disabled="!allowed(day.value)" :class="{ muted: !day.current, selected: day.value === value, today: day.value === today }" @click="choose(day.value)">{{ day.number }}</button></div>
      <div class="calendar-actions"><button type="button" @click="choose('')">Clear</button><button type="button" :disabled="!allowed(today)" @click="choose(today)">Today</button><button type="button" @click="close">Close</button></div>
    </div>
  </div>
</template>

<style scoped>
.date-field { position:relative; min-width:0; }
label { display:block; font-size:14px; font-weight:600; }
label input { display:block; margin-top:7px; min-width:0; width:100%; border:1px solid #b9c4d2; border-radius:5px; padding:10px 46px 10px 10px; font:inherit; font-weight:400; color:#202c3d; background:#fff; }
input::-webkit-calendar-picker-indicator { display:none; }
.calendar-trigger { position:absolute; right:1px; top:24px; bottom:1px; border:0; border-left:1px solid #dce2e9; border-radius:0 5px 5px 0; padding:8px 10px; }
svg { width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:1.6; }
input:focus-visible, select:focus-visible { outline:3px solid #527ba8; outline-offset:2px; }
.calendar { position:absolute; z-index:10; top:100%; right:0; width:310px; max-width:calc(100vw - 40px); margin-top:6px; padding:12px; background:#fff; border:1px solid #b9c4d2; border-radius:8px; box-shadow:0 8px 24px #202c3d26; }
.calendar-heading { display:flex; gap:4px; align-items:center; margin-bottom:12px; }
.calendar-heading button { padding:5px 9px; font-size:20px; }
.calendar-heading select, .calendar-heading input { padding:6px 3px; border:1px solid #b9c4d2; border-radius:4px; background:#fff; color:#202c3d; font:inherit; font-size:13px; min-width:0; }
.calendar-heading select { flex:1; }.calendar-heading input { width:67px; }
.days { display:grid; grid-template-columns:repeat(7, 1fr); gap:3px; text-align:center; }
.weekday { font-size:11px; color:#627084; padding-bottom:5px; }
.days button { padding:7px 0; border:0; font-size:12px; font-weight:400; }
.days button.muted { color:#8b96a5; }.days button.today { box-shadow:inset 0 0 0 1px #527ba8; }.days button.selected { background:#263e5c; color:#fff; }
.days button:disabled { cursor:default; opacity:.35; }
.calendar-actions { display:flex; justify-content:space-between; margin-top:10px; }.calendar-actions button { padding:5px 9px; font-size:12px; }
</style>
