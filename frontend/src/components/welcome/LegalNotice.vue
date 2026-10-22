<script setup lang="ts">
defineProps<{ document: 'terms' | 'privacy' }>()
</script>

<template>
  <article class="legal-copy">
    <p class="legal-date">Updated 21 October 2026</p>
    <template v-if="document === 'terms'">
      <h3>Using Application Tracker</h3>
      <p>Application Tracker helps you organize job applications, contacts, interviews, tasks, and follow-up drafts. You can use its core tracking features without connecting a Google account or an AI agent. A workspace operator may protect a hosted workspace with a password.</p>
      <h3>Your records and responsibilities</h3>
      <p>Only add information you are entitled to use. Keep contact details relevant to your applications, respect other people’s privacy, and do not use the workspace for unlawful activity, unsolicited bulk messaging, or attempts to access someone else’s data.</p>
      <p>You are responsible for checking dates, recipients, attachments, and message content before taking action. Tracking a deadline or marking a follow-up as sent does not itself submit an application or deliver an email.</p>
      <h3>Optional connections</h3>
      <p>Google, sync, notifications, and agent access are optional and managed in Settings. Review the permissions you grant. Connected services have their own terms and privacy policies. An authorized agent can read or change records within the permissions you enable; review its work. Creating a Gmail draft does not send it.</p>
      <h3>Access and backups</h3>
      <p>Protect workspace passwords, agent tokens, devices, and recovery keys. Use Export and your workspace’s backup process to keep copies of important records. Availability depends on the device or server running this workspace and any connected services; interruptions and errors can occur.</p>
      <h3>Information and service limits</h3>
      <p>Records, suggestions, extracted contacts, and generated drafts may be incomplete or incorrect. Application Tracker does not guarantee a job offer, response, delivery, or uninterrupted service. Nothing in these terms limits rights or responsibilities that cannot be limited under applicable law.</p>
      <h3>Workspace operator and changes</h3>
      <p>The workspace operator is the person or organization running this installation. Contact the person who provided this workspace’s address about access, data requests, or any additional hosting terms. If you run it yourself, you control its hosting and backups. Review the date above when these terms change.</p>
    </template>
    <template v-else>
      <h3>Where your information lives</h3>
      <p>Applications, contacts, notes, tasks, interviews, documents, and follow-ups are stored by the backend running this workspace. A local installation stores these on its host device; a hosted installation stores them on its server. They are not stored only in this browser. The workspace operator controls hosting, access, backups, and server logs.</p>
      <h3>Cookies for requested features</h3>
      <ul>
        <li><strong>Workspace login:</strong> a protected hosted workspace uses <code>__Host-tracker-session</code> to keep you signed in. Its lifetime is set by the operator; signing out clears it.</li>
        <li><strong>Google connection:</strong> <code>tracker-google-link</code> protects a connection attempt. It expires after 10 minutes and is cleared when the callback completes.</li>
      </ul>
      <h3>Storage on this browser</h3>
      <p>Browser local storage remembers appearance, navigation and table preferences, the identifier of a registered notification device, and whether you have seen the welcome guide and this notice. These remain until replaced or cleared in your browser. Clearing browser storage does not delete records from the workspace server.</p>
      <p>The phone app’s service worker caches public offline guidance and icons, not your application records. Notification subscriptions are created only when you enable notifications. Remove a subscription in Settings before clearing browser data if you want to stop that device’s notifications.</p>
      <h3>Optional services and sharing</h3>
      <p>Connecting Google allows the capabilities you select, such as Gmail search, Gmail drafts, or Drive app data. Enabling sync stores encrypted workspace data in Google Drive. Enabling agent access allows the permissions configured in Settings. Public-web research sends search queries and visits external sites when requested. Those providers receive the requests needed to perform these features.</p>
      <h3>No advertising or analytics trackers in the app</h3>
      <p>Application Tracker does not include advertising or analytics trackers. This notice explains functional cookies and browser storage; closing it does not grant marketing consent or accept the terms. Extra services added by a hosting operator may have separate notices.</p>
      <h3>Managing your information</h3>
      <p>Use Export for a copy of your records, Settings to manage connections and device notifications, and the application controls to remove records. Disconnecting a service does not erase copies already exported, synced, or backed up. Contact your workspace operator about deletion, retention, backups, or privacy requests for this installation.</p>
    </template>
  </article>
</template>

<style scoped>
.legal-copy { line-height: 1.7; overflow-wrap: anywhere; }
.legal-date { color: var(--at-text-muted); font-size: 13px; margin-top: 0; }
.legal-copy h3 { font-size: 17px; margin: 24px 0 8px; }
.legal-copy p { margin: 0 0 14px; }
.legal-copy ul { padding-left: 22px; }
.legal-copy li { margin-bottom: 10px; }
.legal-copy code { font-size: .9em; }
</style>
