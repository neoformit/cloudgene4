import { defineStore } from 'pinia'
import { getServerInfo } from '@/api/server'

/**
 * Public server info from GET /api/server (SPEC §3.6). The navbar list is already filtered
 * by the server for the current viewer, so `load(true)` after login/logout.
 */
export const useServerStore = defineStore('server', {
  state: () => ({
    name: 'Cloudgene',
    url: '',
    maintenance: false,
    maintenanceMessage: '',
    navbar: [],
    footerHtml: '',
    loaded: false,
    error: null,
  }),

  actions: {
    async load(force = false) {
      if (this.loaded && !force) return
      try {
        const { data } = await getServerInfo()
        this.name = data.name
        this.url = data.url
        this.maintenance = data.maintenance
        this.maintenanceMessage = data.maintenance_message
        this.navbar = data.navbar || []
        this.footerHtml = data.footer_html || ''
        this.loaded = true
        this.error = null
      } catch (err) {
        this.error = err
      }
    },
  },
})
