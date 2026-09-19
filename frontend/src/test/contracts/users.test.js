/**
 * Contract tests for src/api/users.js (profile, API token, admin users/groups — SPEC §3.6)
 * and the account-flow calls of src/api/auth.js.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as usersApi from '@/api/users'
import * as authApi from '@/api/auth'
import { initials, avatarHue } from '@/utils/avatar'
import {
  adminGroupListSchema,
  adminUserListSchema,
  apiTokenSchema,
  profileSchema,
} from '../schemas'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

const ajv = new Ajv()
addFormats(ajv)
global.ajv = ajv

const user = {
  id: 2,
  username: 'alice',
  email: 'alice@example.org',
  full_name: 'Alice Liddell',
  is_active: true,
  is_admin: false,
  groups: ['researchers'],
  date_joined: '2026-09-19T10:00:00Z',
  last_login: null,
}

describe('users API', () => {
  let client
  beforeEach(async () => {
    vi.clearAllMocks()
    client = (await import('@/api/client')).default
  })

  describe('profile', () => {
    it('getProfile → GET /me/ with token metadata only', async () => {
      client.get.mockResolvedValue({ data: { ...user, api_token: { created: '2026-09-19T10:00:00Z' } } })
      const { data } = await usersApi.getProfile()
      expect(client.get).toHaveBeenCalledWith('/me/')
      expect(data).toMatchApiSchema(profileSchema)
      expect(ajv.validate(profileSchema, { ...user, api_token: { token: 'x' } })).toBe(false)
    })

    it('updateProfile → PATCH /me/', async () => {
      client.patch.mockResolvedValue({ data: { ...user, api_token: null } })
      const body = { email: 'new@x.org', current_password: 'Old12345' }
      await usersApi.updateProfile(body)
      expect(client.patch).toHaveBeenCalledWith('/me/', body)
    })

    it('deleteAccount sends the password as the DELETE body', async () => {
      client.delete.mockResolvedValue({ data: { message: 'deleted' } })
      await usersApi.deleteAccount('Secret123')
      expect(client.delete).toHaveBeenCalledWith('/me/', { data: { password: 'Secret123' } })
    })

    it('createApiToken / revokeApiToken', async () => {
      client.post.mockResolvedValue({ data: { token: 'abc123', created: '2026-09-19T10:00:00Z' } })
      const { data } = await usersApi.createApiToken()
      expect(client.post).toHaveBeenCalledWith('/me/token/')
      expect(data).toMatchApiSchema(apiTokenSchema)
      client.delete.mockResolvedValue({ data: { message: 'API token revoked.' } })
      await usersApi.revokeApiToken()
      expect(client.delete).toHaveBeenCalledWith('/me/token/')
    })
  })

  describe('admin users', () => {
    it('listUsers → GET /admin/users/ with params (paginated)', async () => {
      client.get.mockResolvedValue({
        data: { count: 1, next: null, previous: null, results: [{ ...user, is_superuser: false, activated_at: null }] },
      })
      const { data } = await usersApi.listUsers({ search: 'ali', page: 2 })
      expect(client.get).toHaveBeenCalledWith('/admin/users/', { params: { search: 'ali', page: 2 } })
      expect(data).toMatchApiSchema(adminUserListSchema)
    })

    it('groups are names, not objects (the old shape fails the contract)', () => {
      const bad = { count: 1, next: null, previous: null, results: [{ ...user, groups: [{ id: 1, name: 'x' }] }] }
      expect(ajv.validate(adminUserListSchema, bad)).toBe(false)
    })

    it('updateUser / deleteUser / getUser', async () => {
      client.patch.mockResolvedValue({ data: user })
      await usersApi.updateUser(2, { groups: ['researchers'], is_active: false })
      expect(client.patch).toHaveBeenCalledWith('/admin/users/2/', { groups: ['researchers'], is_active: false })
      await usersApi.deleteUser(2)
      expect(client.delete).toHaveBeenCalledWith('/admin/users/2/')
      await usersApi.getUser(2)
      expect(client.get).toHaveBeenCalledWith('/admin/users/2/')
    })
  })

  describe('admin groups', () => {
    it('listGroups → plain array with member_count', async () => {
      client.get.mockResolvedValue({ data: [{ id: 1, name: 'admin', member_count: 1 }] })
      const { data } = await usersApi.listGroups()
      expect(client.get).toHaveBeenCalledWith('/admin/groups/')
      expect(data).toMatchApiSchema(adminGroupListSchema)
    })

    it('createGroup / deleteGroup', async () => {
      client.post.mockResolvedValue({ data: { id: 3, name: 'lab', member_count: 0 } })
      await usersApi.createGroup({ name: 'lab' })
      expect(client.post).toHaveBeenCalledWith('/admin/groups/', { name: 'lab' })
      await usersApi.deleteGroup(3)
      expect(client.delete).toHaveBeenCalledWith('/admin/groups/3/')
    })
  })

  describe('account flows (auth.js)', () => {
    it('activate POSTs the (url-encoded) key', async () => {
      client.post.mockResolvedValue({ data: { status: 'already_active', message: 'ok' } })
      await authApi.activate('a/b')
      expect(client.post).toHaveBeenCalledWith('/auth/activate/a%2Fb/')
    })

    it('confirmPasswordReset posts password (+ confirm) to /auth/password-reset/<token>/', async () => {
      client.post.mockResolvedValue({ data: { message: 'ok' } })
      await authApi.confirmPasswordReset('tok', 'NewPass1', 'NewPass1')
      expect(client.post).toHaveBeenCalledWith('/auth/password-reset/tok/', {
        password: 'NewPass1',
        password_confirm: 'NewPass1',
      })
      await authApi.confirmPasswordReset('tok', 'NewPass1')
      expect(client.post).toHaveBeenLastCalledWith('/auth/password-reset/tok/', { password: 'NewPass1' })
    })

    it('there is no getToken() any more (token is created from the profile)', () => {
      expect(authApi.getToken).toBeUndefined()
    })
  })
})

describe('initials avatar (no external requests)', () => {
  it('uses the full name, else the username', () => {
    expect(initials({ full_name: 'Alice van Liddell', username: 'alice' })).toBe('AL')
    expect(initials({ full_name: '', username: 'bob' })).toBe('BO')
    expect(initials(null)).toBe('?')
  })
  it('hue is stable per user', () => {
    expect(avatarHue({ username: 'alice' })).toBe(avatarHue({ username: 'alice' }))
  })
})
