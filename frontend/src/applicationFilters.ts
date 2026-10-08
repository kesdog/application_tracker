import { reactive } from 'vue'
import type { ApplicationFilters } from './api'
import { applicationOutcomeMeta, applicationStatusMeta, contractLabel, remotePolicyMeta, sourceLabel } from './presentation/applicationPresentation'

export const blankFilters = (): ApplicationFilters => ({ q: '', status: '', outcome: '', company: '', title: '', location: '', contract_type: '', source: '', remote_policy: '', date_from: '', date_to: '', document_filename: '' })
// Keep the last applied view available when navigating to Export.
export const appliedFilters = reactive<ApplicationFilters>(blankFilters())

const filterNames: Record<keyof ApplicationFilters, string> = {
  q: 'Search', status: 'Status', outcome: 'Outcome', company: 'Company', title: 'Position',
  location: 'Location', contract_type: 'Contract', source: 'Source', remote_policy: 'Remote policy',
  date_from: 'Applied from', date_to: 'Applied to', document_filename: 'Document',
}
export function activeFilterLabels(filters: ApplicationFilters): { key: keyof ApplicationFilters; label: string }[] {
  return (Object.keys(filterNames) as (keyof ApplicationFilters)[]).flatMap(key => {
    const value = filters[key]
    if (!value) return []
    let label: string = value
    if (key === 'status') label = applicationStatusMeta[value as keyof typeof applicationStatusMeta]?.label ?? value
    if (key === 'outcome') label = applicationOutcomeMeta[value as keyof typeof applicationOutcomeMeta]?.label ?? value
    if (key === 'contract_type') label = contractLabel(value)
    if (key === 'source') label = sourceLabel(value)
    if (key === 'remote_policy') label = remotePolicyMeta[value]?.label ?? value
    return [{ key, label: `${filterNames[key]}: ${label}` }]
  })
}
