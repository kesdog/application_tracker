<script setup lang="ts">
import { computed } from 'vue'
import type { FollowUpTargetStatus } from '../../api'
import { followupTargetLabels } from '../../presentation/followupTargets'
const props = defineProps<{ status: FollowUpTargetStatus | null }>()
const label = computed(() => props.status ? followupTargetLabels[props.status] : '')
</script>
<template>
  <span v-if="status" class="followup-target" :class="`target-${status.toLowerCase()}`" role="img" :aria-label="label" :title="label">
    <i class="pi pi-envelope" aria-hidden="true" />
  </span>
</template>
<style scoped>
.followup-target { display:inline-flex; flex-shrink:0; align-items:center; justify-content:center; width:30px; height:28px; border-radius:6px; border:1px solid var(--target-edge); background:var(--target-fill); color:var(--target-ink); vertical-align:middle; }
.followup-target i { font-size:17px; }
.target-unknown { --target-fill:#fff1df; --target-ink:#a84305; --target-edge:#f5be82; }
.target-potential { --target-fill:#dff3ff; --target-ink:#075985; --target-edge:#7dd3fc; }
.target-confirmed { --target-fill:#dcfce7; --target-ink:#166534; --target-edge:#86efac; }
.target-sent { --target-fill:#14532d; --target-ink:#ffffff; --target-edge:#166534; }
:global([data-theme="dark"] .target-unknown) { --target-fill:#49290c; --target-ink:#fdba74; --target-edge:#a85e21; }
:global([data-theme="dark"] .target-potential) { --target-fill:#123b58; --target-ink:#7dd3fc; --target-edge:#307ba5; }
:global([data-theme="dark"] .target-confirmed) { --target-fill:#173f2b; --target-ink:#86efac; --target-edge:#43825b; }
:global([data-theme="dark"] .target-sent) { --target-fill:#14532d; --target-ink:#ffffff; --target-edge:#4d9b69; }
</style>
