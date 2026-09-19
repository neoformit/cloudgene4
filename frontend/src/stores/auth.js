import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'

/**
 * Session-backed auth state. Nothing is persisted in localStorage: the source of truth
 * is the Django session, read from GET /api/auth/me on boot (router guards await it).
 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    booted: false,
    _bootPromise: null,
  }),

  getters: {
    isLoggedIn: (state) => !!state.user,
    isAdmin: (state) => !!state.user?.is_admin,
  },

  actions: {
    /** Fetch the current session once; concurrent callers share the same promise. */
    boot() {
      if (this.booted) return Promise.resolve(this.user)
      if (!this._bootPromise) {
        this._bootPromise = this.refresh().finally(() => {
          this.booted = true
          this._bootPromise = null
        })
      }
      return this._bootPromise
    },

    /** Re-read /auth/me (e.g. after the session may have changed). */
    async refresh() {
      try {
        const { data } = await authApi.me()
        this.user = data.authenticated ? data.user : null
      } catch {
        // Server unreachable or error: behave as anonymous rather than blocking the app.
        this.user = null
      }
      return this.user
    },

    async login(username, password) {
      const { data } = await authApi.login(username, password)
      this.user = data.user
      this.booted = true
      return data.user
    },

    async logout() {
      try {
        await authApi.logout()
      } finally {
        this._clear()
      }
    },

    /** Local reset (e.g. the server answered 401: session expired). */
    _clear() {
      this.user = null
    },

    updateUser(user) {
      this.user = user
    },
  },
})
