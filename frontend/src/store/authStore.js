/**
 * Zustand store — Authentication state
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi } from '../api/client'

const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,

      login: async (email, password) => {
        const { data } = await authApi.login({ email, password })
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        const me = await authApi.me()
        set({ user: me.data, isAuthenticated: true })
        return me.data
      },

      logout: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ user: null, isAuthenticated: false })
      },

      fetchMe: async () => {
        try {
          const me = await authApi.me()
          set({ user: me.data, isAuthenticated: true })
        } catch {
          get().logout()
        }
      },
    }),
    {
      name: 'steelcad-auth',
      // Persist only what routing needs across a hard refresh (auth flag +
      // role for RoleRoute). Email/name are PII and must not sit in
      // localStorage, where any injected script could read them — fetchMe()
      // rehydrates the full profile from /auth/me on boot.
      partialize: (s) => ({
        isAuthenticated: s.isAuthenticated,
        user: s.user ? { role: s.user.role } : null,
      }),
    }
  )
)

export default useAuthStore
