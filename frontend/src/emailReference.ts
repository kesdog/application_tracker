/** References stay compatible with the saved text field: one message per line. */
export function emailReferences(reference: string | null): string[] {
  return [...new Set((reference ?? '').split(/\r?\n/).map(value => value.trim()).filter(Boolean))]
}

/** Compact lists prefer a direct, account-bound message over a subject search. */
export function primaryEmailReference(reference: string | null): string | null {
  const references = emailReferences(reference)
  const direct = references.filter(value => /^https?:\/\//i.test(value) && emailReferenceUrl(value))
  return direct.find(value => {
    const url = new URL(value)
    return url.hostname === 'mail.google.com' && url.searchParams.has('authuser') && !url.hash.startsWith('#search/')
  }) ?? direct.find(value => !new URL(value).hash.startsWith('#search/'))
    ?? references.find(value => /^\[?Gmail:/i.test(value) && emailReferenceUrl(value))
    ?? references.find(value => emailReferenceUrl(value)?.includes('#search/rfc822msgid%3A'))
    ?? references.find(value => emailReferenceUrl(value)) ?? references[0] ?? null
}

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
