/**
 * Contract tests for authentication API endpoints
 * 
 * These tests validate that the frontend API client correctly handles
 * authentication responses and error formats from the backend.
 */

import { describe, it, expect, beforeAll, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as authApi from '@/api/auth'
import { authResponseSchema, userSchema, validationErrorSchema } from '../schemas'

// Mock the HTTP client to avoid real network requests
vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn()
  }
}))

const ajv = new Ajv()
addFormats(ajv)
global.ajv = ajv

describe('Authentication API Contracts', () => {
  beforeAll(() => {
    // Reset all mocks before each test suite
    vi.clearAllMocks()
  })

  describe('Login Contract', () => {
    it('should receive valid authentication response on successful login', async () => {
      const mockResponse = {
        data: {
          token: 'abc123token',
          user: {
            id: 1,
            username: 'testuser',
            email: 'test@example.com',
            full_name: 'Test User',
            is_admin: false
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const response = await authApi.login('testuser', 'password123')

      // Verify the API was called correctly
      expect(client.default.post).toHaveBeenCalledWith('/auth/login/', {
        username: 'testuser',
        password: 'password123'
      })

      // Validate response structure matches contract
      expect(response.data).toMatchApiSchema(authResponseSchema)
      expect(response.data.user).toMatchApiSchema(userSchema)
    })

    it('should handle validation errors with proper field mapping', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            username: ['This field is required.'],
            password: ['This field is required.']
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await authApi.login('', '')
        expect.fail('Expected login to throw error')
      } catch (error) {
        expect(error.response.status).toBe(400)
        expect(error.response.data).toMatchApiSchema(validationErrorSchema)
        expect(error.response.data).toHaveApiField('username')
        expect(error.response.data).toHaveApiField('password')
      }
    })

    it('should handle authentication errors correctly', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            non_field_errors: ['Unable to log in with provided credentials.']
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await authApi.login('testuser', 'wrongpassword')
        expect.fail('Expected login to throw error')
      } catch (error) {
        expect(error.response.status).toBe(400)
        expect(error.response.data).toHaveApiField('non_field_errors')
      }
    })
  })

  describe('Registration Contract', () => {
    it('should receive valid authentication response on successful registration', async () => {
      const mockResponse = {
        data: {
          token: 'newusertoken123',
          user: {
            id: 2,
            username: 'newuser',
            email: 'new@example.com',
            full_name: 'New User',
            is_admin: false
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const registrationData = {
        username: 'newuser',
        email: 'new@example.com',
        password: 'strongpassword123',
        full_name: 'New User'
      }

      const response = await authApi.register(registrationData)

      expect(client.default.post).toHaveBeenCalledWith('/auth/register/', registrationData)
      expect(response.data).toMatchApiSchema(authResponseSchema)
    })

    it('should handle registration validation errors', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            username: ['A user with that username already exists.'],
            email: ['Enter a valid email address.']
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await authApi.register({
          username: 'existinguser',
          email: 'invalid-email',
          password: 'password123'
        })
        expect.fail('Expected registration to throw error')
      } catch (error) {
        expect(error.response.status).toBe(400)
        expect(error.response.data).toMatchApiSchema(validationErrorSchema)
        expect(error.response.data).toHaveApiField('username')
        expect(error.response.data).toHaveApiField('email')
      }
    })
  })

  describe('Password Reset Contract', () => {
    it('should handle successful password reset request', async () => {
      const mockResponse = {
        data: { message: 'Password reset email sent.' }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const response = await authApi.requestPasswordReset('test@example.com')

      expect(client.default.post).toHaveBeenCalledWith('/auth/password-reset/', {
        email: 'test@example.com'
      })
      expect(response.data).toHaveApiField('message')
    })

    it('should handle password reset validation errors', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            email: ['Enter a valid email address.']
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await authApi.requestPasswordReset('invalid-email')
        expect.fail('Expected password reset to throw error')
      } catch (error) {
        expect(error.response.status).toBe(400)
        expect(error.response.data).toHaveApiField('email')
      }
    })
  })

  describe('Logout Contract', () => {
    it('should handle successful logout', async () => {
      const mockResponse = {
        data: { message: 'Successfully logged out.' }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const response = await authApi.logout()

      expect(client.default.post).toHaveBeenCalledWith('/auth/logout/')
      expect(response).toBeValidApiResponse()
    })
  })
})