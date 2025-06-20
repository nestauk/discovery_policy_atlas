import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { SearchParams } from '@/types/search'

interface SearchStoreState {
  searchParams: SearchParams
  setSearchParams: (params: SearchParams) => void
  reset: () => void
}

const defaultParams: SearchParams = {
  query: '',
  source: 'overton',
  max_results: 10,
  semantic_search: false,
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