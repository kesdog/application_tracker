<script setup lang="ts">
defineProps<{ label: string }>()
</script>
<template><span class="busy-indicator" role="status"><span class="spinner" aria-hidden="true" />{{ label }}</span></template>
<style scoped>
.busy-indicator{display:inline-flex;align-items:center;gap:9px}.spinner{width:16px;height:16px;border:2px solid var(--at-border);border-top-color:var(--at-primary);border-radius:50%;animation:turn .8s linear infinite;flex-shrink:0}@keyframes turn{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinner{animation:none}}
</style>
