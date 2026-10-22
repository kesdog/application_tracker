import { expect, it } from 'vitest'
import { detectJobSource } from '../../src/applicationOptions'
import { positionLabel } from '../../src/presentation/applicationPresentation'
import { emailReferences, emailReferenceUrl } from '../../src/emailReference'

it('detects board sources without accepting lookalike hosts', () => {
  for (const [url, expected] of [
    ['https://fr.indeed.com/viewjob?jk=1', 'INDEED'],
    ['https://www.linkedin.com/jobs/view/1', 'LINKEDIN'],
    ['https://www.free-work.com/fr/tech-it/offre/1', 'FREEWORK'],
    ['https://www.hellowork.com/fr-fr/emplois/1.html', 'HELLOWORK'],
    ['https://indeed.com.evil.example/jobs/1', 'OTHER'],
    ['https://example.com/jobs/1', 'OTHER'],
    ['', 'OTHER'],
  ] as const) expect(detectJobSource(url), url).toBe(expected)
})

it('removes edge contract metadata while keeping the actual position text', () => {
  for (const [title, expected] of [
    ['CDI - Engineer', 'Engineer'], ['Alternance - Développeur C# .NET', 'Développeur C# .NET'],
    ['ALTERNANCE DÉVELOPPEUR FULL STACK', 'DÉVELOPPEUR FULL STACK'], ['Développeur (H/F) - Alternance', 'Développeur (H/F)'],
    ['Développeur FullStack H/F - Stage - Alternance', 'Développeur FullStack H/F'],
    ['Stage 6 mois ou Alternance - Full Stack', 'Full Stack'], ['Engineering stage manager', 'Engineering stage manager'],
  ] as const) expect(positionLabel(title), title).toBe(expected)
})

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

it('keeps references separate, drops duplicate lines and preserves punctuation in subjects and links', () => {
  const references = emailReferences(' [Gmail:1a123]\r\nYour application, Engineer; Example\n[Gmail:1a123]\nhttps://outlook.office.com/mail/id/example?x=1&y=2\n')
  expect(references).toEqual(['[Gmail:1a123]', 'Your application, Engineer; Example', 'https://outlook.office.com/mail/id/example?x=1&y=2'])
  expect(emailReferences(null)).toEqual([])
})
