<script setup lang="ts">
import { t, messageText } from '../../i18n'

import { computed, ref } from 'vue'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'

const props = defineProps<{
  label: string
  tabs: { value: string; label: string; icon?: string; count?: number }[]
  initial?: string
}>()
const model = defineModel<string>()
const localActive = ref(props.initial ?? props.tabs[0]?.value ?? '')
const active = computed({
  get: () => model.value ?? localActive.value,
  set: (value: string | number) => { localActive.value = String(value); model.value = String(value) },
})
</script>

<template>
  <Tabs v-model:value="active" class="page-tabs" :lazy="false" :show-navigators="false">
    <TabList :pt="{ content: { 'aria-label': label } }">
      <Tab v-for="tab in tabs" :key="tab.value" :value="tab.value">
        <i v-if="tab.icon" :class="`pi ${tab.icon}`" aria-hidden="true" />
        <span>{{ messageText(String((tab.label) ?? '')) }}</span><span v-if="tab.count !== undefined" class="tab-count">{{ tab.count }}</span>
      </Tab>
    </TabList>
    <TabPanels>
      <TabPanel v-for="tab in tabs" :key="tab.value" :value="tab.value">
        <slot :name="tab.value" />
      </TabPanel>
    </TabPanels>
  </Tabs>
</template>

<style scoped>
.page-tabs { min-width:0; margin-block:20px; }
.page-tabs :deep(.p-tablist-content) { flex-wrap:wrap; overflow:visible; gap:4px; border:0; padding:4px; background:var(--at-surface-muted); border-radius:10px; }
.page-tabs :deep(.p-tab) { display:flex; align-items:center; justify-content:center; flex:0 1 auto; gap:8px; min-height:42px; padding:10px 14px; border:0; border-radius:7px; background:transparent; color:var(--at-text-muted); font-size:13px; font-weight:600; white-space:nowrap; }
.page-tabs :deep(.p-tab:hover) { color:var(--at-text); background:var(--at-surface); }
.page-tabs :deep(.p-tab[data-p-active="true"]) { color:var(--at-primary); background:var(--at-surface); box-shadow:0 1px 3px #00000012; }
.page-tabs :deep(.p-tablist-active-bar) { display:none; }
.page-tabs :deep(.p-tabpanels), .page-tabs :deep(.p-tabpanel) { padding:0; background:transparent; color:var(--at-text); }
.page-tabs :deep(.p-tabpanel) { padding-top:16px; }
.tab-count { font-size:11px; padding:2px 6px; border-radius:10px; background:var(--at-background); color:var(--at-text-muted); }
@media(max-width:600px) { .page-tabs :deep(.p-tab) { flex:1 0 auto; padding:10px; gap:6px; font-size:12px; }.page-tabs :deep(.p-tab i) { display:none; } }
</style>
