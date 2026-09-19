import { defineStore } from 'pinia'
import { api } from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('elh_token') || sessionStorage.getItem('token') || sessionStorage.token || null,
    loading: false,
    error: null
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    role: (state) => state.user?.role || '',
    username: (state) => state.user?.username || '',
    isAdmin: (state) => ['super_admin', 'admin'].includes(state.user?.role)
  },
  actions: {
    async login(username, password) {
      this.loading = true
      this.error = null
      try {
        const data = await api('/api/auth/login', {
          method: 'POST',
          body: JSON.stringify({ username, password })
        })
        this.token = data.access_token || data.token
        localStorage.setItem('elh_token', this.token)
        if (data.user) {
          this.user = data.user
        } else {
          await this.fetchMe()
        }
        return true
      } catch (err) {
        this.error = err.message
        return false
      } finally {
        this.loading = false
      }
    },
    async fetchMe() {
      if (!this.token) return null
      try {
        const data = await api('/api/auth/me')
        this.user = data
        return data
      } catch (err) {
        console.warn('Failed to refresh user profile:', err)
        if (!this.user) {
          this.logout()
        }
        return null
      }
    },
    logout() {
      this.user = null
      this.token = null
      localStorage.removeItem('elh_token')
      sessionStorage.removeItem('token')
      delete sessionStorage.token
      if (window.logout) {
        window.logout()
      } else {
        window.location.hash = '#login'
      }
    }
  }
})
