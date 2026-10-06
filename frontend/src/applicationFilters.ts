import { reactive } from 'vue'
import type { ApplicationFilters } from './api'

export const blankFilters = (): ApplicationFilters => ({ q: '', status: '', outcome: '', company: '', title: '', location: '', contract_type: '', source: '', remote_policy: '', date_from: '', date_to: '', document_filename: '' })
// Keep the last applied view available when navigating to Export.
export const appliedFilters = reactive<ApplicationFilters>(blankFilters())
