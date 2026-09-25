import { expect, it } from 'vitest'
import { detectJobSource } from './applicationOptions'

it.each([
  ['https://fr.indeed.com/viewjob?jk=1', 'INDEED'],
  ['https://www.linkedin.com/jobs/view/1', 'LINKEDIN'],
  ['https://www.free-work.com/fr/tech-it/offre/1', 'FREEWORK'],
  ['https://www.hellowork.com/fr-fr/emplois/1.html', 'HELLOWORK'],
  ['https://indeed.com.evil.example/jobs/1', 'OTHER'],
  ['https://example.com/jobs/1', 'OTHER'],
  ['', 'OTHER'],
])('detects %s as %s', (url, expected) => {
  expect(detectJobSource(url)).toBe(expected)
})
