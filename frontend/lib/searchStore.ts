import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { SearchParams } from '@/types/search'
import { SEARCH_DEFAULTS } from './constants'

interface SearchStoreState {
  searchParams: SearchParams
  setSearchParams: (params: SearchParams) => void
  reset: () => void
}

const defaultParams: SearchParams = {
  query: '',
  source: SEARCH_DEFAULTS.SOURCE,
  max_results: SEARCH_DEFAULTS.MAX_RESULTS,
  semantic_search: SEARCH_DEFAULTS.SEMANTIC_SEARCH,
}

export const useSearchStore = create<SearchStoreState>()(
  persist(
    (set) => ({
      searchParams: defaultParams,
      setSearchParams: (params) => set({ searchParams: params }),
      reset: () => set({ searchParams: defaultParams }),
    }),
    {
      name: 'search-params', // storage key
      partialize: (state) => ({ searchParams: state.searchParams }),
    }
  )
) 