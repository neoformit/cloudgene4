/**
 * Server store: state from GET /api/server (navbar from settings.yaml, footer, maintenance).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api/server', () => ({
  getServerInfo: vi.fn(),
  getPage: vi.fn(),
}))

const payload = {
  name: 'My Service',
  url: 'https://x.org',
  maintenance: true,
  maintenance_message: 'Back soon',
  navbar: [
    { title: 'Home', url: '/', icon: '', admin_only: false, auth_only: false },
    { title: 'About', url: '/pages/about', icon: 'info', admin_only: false, auth_only: false },
  ],
  footer_html: '<p>Footer</p>',
}

describe('server store', () => {
  let api, useServerStore

  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api = await import('@/api/server')
    ;({ useServerStore } = await import('@/stores/server'))
  })

  it('loads name, maintenance, navbar and footer', async () => {
    api.getServerInfo.mockResolvedValue({ data: payload })
    const store = useServerStore()
    await store.load()
    expect(store.name).toBe('My Service')
    expect(store.maintenance).toBe(true)
    expect(store.maintenanceMessage).toBe('Back soon')
    expect(store.navbar.map((i) => i.title)).toEqual(['Home', 'About'])
    expect(store.footerHtml).toBe('<p>Footer</p>')
    expect(store.loaded).toBe(true)
  })

  it('loads once unless forced (navbar depends on the viewer)', async () => {
    api.getServerInfo.mockResolvedValue({ data: payload })
    const store = useServerStore()
    await store.load()
    await store.load()
    expect(api.getServerInfo).toHaveBeenCalledTimes(1)
    api.getServerInfo.mockResolvedValue({ data: { ...payload, navbar: [] } })
    await store.load(true)
    expect(api.getServerInfo).toHaveBeenCalledTimes(2)
    expect(store.navbar).toEqual([])
  })

  it('keeps defaults and records the error when the request fails', async () => {
    api.getServerInfo.mockRejectedValue(new Error('Network Error'))
    const store = useServerStore()
    await store.load()
    expect(store.loaded).toBe(false)
    expect(store.navbar).toEqual([])
    expect(store.error).toBeTruthy()
  })
})
