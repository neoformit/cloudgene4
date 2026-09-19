/**
 * Contract tests for the auth API module (SPEC §3.4 session auth, §3.5 error envelope).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as authApi from '@/api/auth'
import { authResponseSchema, meResponseSchema, userSchema, validationErrorSchema } from '../schemas'

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

const ajv = new Ajv()
addFormats(ajv)
global.ajv = ajv

const user = {
  id: 1,
  username: 'testuser',
  email: 'test@example.com',
  full_name: 'Test User',
  is_admin: false,
}

const envelope = (message, code = 'invalid', fields = {}) => ({
  error: { message, code, fields },
})

describe('Authentication API Contracts', () => {
  let client

  beforeEach(async () => {
    vi.clearAllMocks()
    client = (await import('@/api/client')).default
  })

  describe('Session', () => {
    it('me() calls GET /auth/me/ and accepts both anonymous and authenticated shapes', async () => {
      client.get.mockResolvedValue({ data: { authenticated: false, user: null } })
      let response = await authApi.me()
      expect(client.get).toHaveBeenCalledWith('/auth/me/')
      expect(response.data).toMatchApiSchema(meResponseSchema)

      client.get.mockResolvedValue({ data: { authenticated: true, user } })
      response = await authApi.me()
      expect(response.data).toMatchApiSchema(meResponseSchema)
    })

    it('login() posts credentials and receives {user} (no token)', async () => {
      client.post.mockResolvedValue({ data: { user } })
      const response = await authApi.login('testuser', 'password123')
      expect(client.post).toHaveBeenCalledWith('/auth/login/', {
        username: 'testuser',
        password: 'password123',
      })
      expect(response.data).toMatchApiSchema(authResponseSchema)
      expect(response.data.user).toMatchApiSchema(userSchema)
    })

    it('an old token-style login response no longer matches the contract', () => {
      expect(ajv.validate(authResponseSchema, { token: 'abc', user })).toBe(false)
    })

    it('login field errors arrive in error.fields', async () => {
      client.post.mockRejectedValue({
        response: {
          status: 400,
          data: envelope('username: This field is required.', 'invalid', {
            username: ['This field is required.'],
            password: ['This field is required.'],
          }),
        },
      })
      await expect(authApi.login('', '')).rejects.toSatisfy((error) => {
        expect(error.response.data).toMatchApiSchema(validationErrorSchema)
        expect(error.response.data.error.fields).toHaveApiField('username')
        expect(error.response.data.error.fields).toHaveApiField('password')
        return true
      })
    })

    it('bad credentials are a non-field error message', async () => {
      client.post.mockRejectedValue({
        response: { status: 400, data: envelope('Invalid username or password.') },
      })
      await expect(authApi.login('testuser', 'wrong')).rejects.toSatisfy((error) => {
        expect(error.response.data).toMatchApiSchema(validationErrorSchema)
        expect(error.response.data.error.message).toBe('Invalid username or password.')
        return true
      })
    })

    it('logout() posts to /auth/logout/', async () => {
      client.post.mockResolvedValue({ status: 200, data: { message: 'Logged out.' } })
      const response = await authApi.logout()
      expect(client.post).toHaveBeenCalledWith('/auth/logout/')
      expect(response).toBeValidApiResponse()
    })
  })

  describe('Registration', () => {
    it('register() posts the form and receives {user, message}', async () => {
      client.post.mockResolvedValue({ data: { user: { ...user, is_active: false }, message: 'ok' } })
      const data = {
        username: 'newuser',
        email: 'new@example.com',
        password: 'StrongPass123',
        full_name: 'New User',
      }
      const response = await authApi.register(data)
      expect(client.post).toHaveBeenCalledWith('/auth/register/', data)
      expect(response.data.user).toMatchApiSchema(userSchema)
    })

    it('registration validation errors arrive in error.fields', async () => {
      client.post.mockRejectedValue({
        response: {
          status: 400,
          data: envelope('username: taken', 'invalid', {
            username: ['A user with that username already exists.'],
            email: ['Enter a valid email address.'],
          }),
        },
      })
      await expect(authApi.register({})).rejects.toSatisfy((error) => {
        expect(error.response.data).toMatchApiSchema(validationErrorSchema)
        expect(error.response.data.error.fields).toHaveApiField('username')
        expect(error.response.data.error.fields).toHaveApiField('email')
        return true
      })
    })
  })

  describe('Password reset', () => {
    it('requestPasswordReset() posts the e-mail', async () => {
      client.post.mockResolvedValue({ data: { message: 'Password reset email sent.' } })
      const response = await authApi.requestPasswordReset('test@example.com')
      expect(client.post).toHaveBeenCalledWith('/auth/password-reset/', {
        email: 'test@example.com',
      })
      expect(response.data).toHaveApiField('message')
    })
  })
})
