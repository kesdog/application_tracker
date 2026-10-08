<script setup lang="ts">
import type { Application } from '../../api'
import { applicationOutcomeMeta } from '../../presentation/applicationPresentation'
import AppTag from '../shared/AppTag.vue'
defineProps<{ outcome: Application['outcome'] }>()
</script>
<template><AppTag v-if="outcome" v-bind="applicationOutcomeMeta[outcome]" /><span v-else aria-label="No outcome">—</span></template>
