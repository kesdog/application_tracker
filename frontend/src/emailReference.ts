/** Open direct mailbox links, or find a saved message ID/subject in Gmail. */
export function emailReferenceUrl(reference: string | null): string | null {
  const value = reference?.trim()
  if (!value) return null
  if (/^https?:\/\//i.test(value)) {
    try { return new URL(value).href } catch { return null }
  }
  const gmailId = value.match(/^\[?Gmail:\s*([a-f0-9]+)\]?$/i)?.[1]
  if (gmailId) return `https://mail.google.com/mail/u/0/#all/${gmailId}`
  const messageId = value.match(/^(?:Message-ID:\s*)?<([^<>\s]+@[^<>\s]+)>$/i)?.[1]
    ?? value.match(/^Message-ID:\s*([^\s]+)$/i)?.[1]
  if (!messageId && /^[a-z][a-z0-9+.-]*:/i.test(value)) return null
  const query = messageId ? `rfc822msgid:${messageId}` : value
  return `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(query)}`
}
