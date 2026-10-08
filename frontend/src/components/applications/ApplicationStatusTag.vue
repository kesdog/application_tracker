<script setup lang="ts">
import type { Application } from '../../api'
import { applicationStatusMeta } from '../../presentation/applicationPresentation'
import AppTag from '../shared/AppTag.vue'
defineProps<{ status: Application['status'] }>()
</script>
<template><AppTag v-bind="applicationStatusMeta[status]" /></template>
