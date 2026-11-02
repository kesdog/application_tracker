import { t } from './i18n'
export type ContactType = 'EMAIL' | 'PHONE'
export type RemotePolicy = 'FULL_REMOTE' | 'HYBRID' | 'IN_PERSON'
export type JobSource = 'INDEED' | 'LINKEDIN' | 'FREEWORK' | 'HELLOWORK' | 'OTHER'

export const contactTypes: { value: ContactType; label: string }[] = [
  { value: 'EMAIL', get label() { return t("Email") } }, { value: 'PHONE', get label() { return t("Phone") } },
]
export const remotePolicies: { value: RemotePolicy; label: string }[] = [
  { value: 'FULL_REMOTE', get label() { return t("Full remote") } },
  { value: 'HYBRID', get label() { return t("Hybrid") } },
  { value: 'IN_PERSON', get label() { return t("In person") } },
]
export const jobSources: { value: JobSource; label: string }[] = [
  { value: 'INDEED', get label() { return t("Indeed") } },
  { value: 'LINKEDIN', get label() { return t("LinkedIn") } },
  { value: 'FREEWORK', get label() { return t("Free-Work") } },
  { value: 'HELLOWORK', get label() { return t("HelloWork") } },
  { value: 'OTHER', get label() { return t("Other") } },
]

const boardDomains: { source: JobSource; domains: string[] }[] = [
  { source: 'INDEED', domains: ['indeed.com', 'indeed.fr', 'indeed.co.uk', 'indeed.de'] },
  { source: 'LINKEDIN', domains: ['linkedin.com'] },
  { source: 'FREEWORK', domains: ['free-work.com'] },
  { source: 'HELLOWORK', domains: ['hellowork.com'] },
]

export function detectJobSource(rawUrl: string): JobSource {
  try {
    const url = new URL(rawUrl.trim())
    if (!['http:', 'https:'].includes(url.protocol)) return 'OTHER'
    const host = url.hostname.toLowerCase().replace(/\.$/, '')
    return boardDomains.find(({ domains }) => domains.some(domain => host === domain || host.endsWith(`.${domain}`)))?.source ?? 'OTHER'
  } catch {
    return 'OTHER'
  }
}

export const remotePolicyLabel = (value: string | null) => remotePolicies.find(option => option.value === value)?.label ?? value ?? t("Not provided")
export const jobSourceLabel = (value: string | null) => jobSources.find(option => option.value === value)?.label ?? value ?? t("Not provided")
