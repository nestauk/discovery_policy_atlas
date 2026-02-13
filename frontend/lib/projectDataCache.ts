import { create } from 'zustand'

/**
 * In-memory cache for expensive, per-project API responses.
 *
 * Data survives tab switches (component unmount/remount) but is NOT persisted
 * to localStorage — a page refresh or sign-out clears it automatically.
 */

type CacheKey = 'navigator' | 'navigatorOverview' | 'summary' | 'charts'

interface ProjectDataCacheState {
  data: Record<string, unknown>

  getCached: (key: CacheKey, projectId: string) => unknown | undefined
  setCache: (key: CacheKey, projectId: string, value: unknown) => void
  invalidateProject: (projectId: string) => void
  clearAll: () => void
}

const buildKey = (key: CacheKey, projectId: string) => `${key}:${projectId}`

export const useProjectDataCache = create<ProjectDataCacheState>((set, get) => ({
  data: {},

  getCached: (key, projectId) => get().data[buildKey(key, projectId)],

  setCache: (key, projectId, value) =>
    set((state) => ({
      data: { ...state.data, [buildKey(key, projectId)]: value },
    })),

  invalidateProject: (projectId) =>
    set((state) => {
      const next: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(state.data)) {
        if (!k.endsWith(`:${projectId}`)) next[k] = v
      }
      return { data: next }
    }),

  clearAll: () => set({ data: {} }),
}))

