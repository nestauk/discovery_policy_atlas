import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const DEFAULT_USER_CONTEXT =
  'I am a senior UK policy advisor in central government. I need evidence synthesised into concise, actionable briefings suitable for ministerial audiences.'

interface UserProfileState {
  userContext: string
  setUserContext: (context: string) => void
}

export const useUserProfileStore = create<UserProfileState>()(
  persist(
    (set) => ({
      userContext: DEFAULT_USER_CONTEXT,
      setUserContext: (context) => set({ userContext: context }),
    }),
    {
      name: 'user-profile-storage',
    },
  ),
)
