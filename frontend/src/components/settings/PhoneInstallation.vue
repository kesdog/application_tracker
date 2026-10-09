<script setup lang="ts">
import { installPhoneShell, phoneShell } from '../../pwa'
</script>
<template>
  <section class="phone-panel" aria-labelledby="phone-heading"><h3 id="phone-heading">Use on your phone</h3>
    <p v-if="phoneShell.installed">Application Tracker is running as an installed app.</p><template v-else><p>Open your hosted workspace address on your phone, sign in, then add it to your home screen.</p><button v-if="phoneShell.available" type="button" @click="installPhoneShell">Install Application Tracker</button><ul><li>iPhone or iPad: in Safari, open Share and choose Add to Home Screen.</li><li>Android: choose Install app or Add to Home screen from your browser menu.</li></ul></template>
    <p v-if="phoneShell.message" role="status">{{ phoneShell.message }}</p><p>Reconnect to view and edit your applications. Enable phone reminders separately below after installing. Your follow-up queue stays available when notification permission is declined.</p>
  </section>
</template>
<style scoped>.phone-panel{margin:20px 0;padding:24px;border:1px solid var(--at-border);border-radius:8px;background:var(--at-surface)}p,li{color:var(--at-text-muted);line-height:1.6}li{margin:8px 0}@media(max-width:650px){.phone-panel{padding:16px}}</style>
