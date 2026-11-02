<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { googleLogin } from '../../googleAuth'
import type { GoogleConnection } from '../../api'
import PhonePairingLink from './PhonePairingLink.vue'
const connection = ref<GoogleConnection | null>(null), error = ref('')
onMounted(async () => { try { connection.value = await googleLogin.status() } catch { error.value = 'Unable to check Google. Open Connections and refresh your connection.' } })
</script>
<template>
  <PhonePairingLink :drive-ready="Boolean(connection?.capabilities.drive)" :account-email="connection?.email" />
  <p v-if="error" role="alert">{{ error }}</p>
  <p v-if="!connection?.capabilities.drive"><a href="#/settings?tab=connections">Manage Google connection</a></p>
</template>
