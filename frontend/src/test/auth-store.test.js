/**
 * Auth store + router guards: session boot from /api/auth/me, no localStorage.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api/auth', () => ({
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

// Route components are irrelevant for guard tests
vi.mock('@/views/public/HomeView.vue', () => ({ default: { template: '<div/>' } }))

const user = { id: 1, username: 'alice', is_admin: false }
const admin = { id: 2, username: 'root', is_admin: true }

describe('auth store', () => {
  let authApi, useAuthStore

  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    authApi = await import('@/api/auth')
    ;({ useAuthStore } = await import('@/stores/auth'))
  })

  it('boots from /auth/me exactly once, even with concurrent callers', async () => {
    authApi.me.mockResolvedValue({ data: { authenticated: true, user } })
    const auth = useAuthStore()
    expect(auth.isLoggedIn).toBe(false)
    await Promise.all([auth.boot(), auth.boot()])
    await auth.boot()
    expect(authApi.me).toHaveBeenCalledTimes(1)
    expect(auth.isLoggedIn).toBe(true)
    expect(auth.user.username).toBe('alice')
    expect(localStorage.length).toBe(0)
  })

  it('anonymous and failing /me both mean logged out', async () => {
    authApi.me.mockResolvedValue({ data: { authenticated: false, user: null } })
    const auth = useAuthStore()
    await auth.boot()
    expect(auth.isLoggedIn).toBe(false)

    authApi.me.mockRejectedValue(new Error('Network Error'))
    await auth.refresh()
    expect(auth.isLoggedIn).toBe(false)
  })

  it('login stores the returned user; logout clears it even if the call fails', async () => {
    authApi.login.mockResolvedValue({ data: { user: admin } })
    const auth = useAuthStore()
    await auth.login('root', 'pw')
    expect(auth.isAdmin).toBe(true)
    expect(localStorage.getItem('cg_token')).toBeNull()

    authApi.logout.mockRejectedValue(new Error('boom'))
    await expect(auth.logout()).rejects.toThrow()
    expect(auth.isLoggedIn).toBe(false)
  })
})

describe('router guards', () => {
  let authApi, router

  async function freshRouter() {
    vi.resetModules()
    setActivePinia(createPinia())
    authApi = await import('@/api/auth')
    router = (await import('@/router')).default
    return router
  }

  it('waits for boot and redirects anonymous users to /login?next=', async () => {
    await freshRouter()
    authApi.me.mockResolvedValue({ data: { authenticated: false, user: null } })
    await router.push('/jobs/abc')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.next).toBe('/jobs/abc')
  })

  it('lets a logged-in user through after a hard refresh (session from /me)', async () => {
    await freshRouter()
    authApi.me.mockResolvedValue({ data: { authenticated: true, user } })
    await router.push('/jobs')
    expect(router.currentRoute.value.path).toBe('/jobs')
  })

  it('sends non-admins away from admin routes', async () => {
    await freshRouter()
    authApi.me.mockResolvedValue({ data: { authenticated: true, user } })
    await router.push('/admin/users')
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('admins can open admin routes', async () => {
    await freshRouter()
    authApi.me.mockResolvedValue({ data: { authenticated: true, user: admin } })
    await router.push('/admin')
    expect(router.currentRoute.value.path).toBe('/admin')
  })
})
