import { expect, it } from 'vitest'
import { emailReferenceUrl } from './emailReference'

it('keeps direct Gmail and Outlook mailbox links', () => {
  for (const url of ['https://mail.google.com/mail/u/0/#all/1a123', 'https://outlook.office.com/mail/id/example']) expect(emailReferenceUrl(url)).toBe(url)
})

it('opens saved Gmail IDs and searches RFC message IDs or subjects', () => {
  expect(emailReferenceUrl('[Gmail:1a123]')).toBe('https://mail.google.com/mail/u/0/#all/1a123')
  expect(emailReferenceUrl('Message-ID: <abc@example.com>')).toBe('https://mail.google.com/mail/u/0/#search/rfc822msgid%3Aabc%40example.com')
  expect(emailReferenceUrl('Your application to Acme')).toBe('https://mail.google.com/mail/u/0/#search/Your%20application%20to%20Acme')
})

it('does not turn executable or local references into links', () => {
  for (const reference of [null, '', 'javascript:alert(1)', 'data:text/html,bad', 'file:///private/message']) expect(emailReferenceUrl(reference)).toBeNull()
})
