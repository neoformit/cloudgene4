/**
 * Tests for the HTTP client: CSRF header, error-envelope helpers, 401 handling.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import client, {
  apiErrorMessage,
  apiFieldErrors,
  apiErrorCode,
  onUnauthorized,
  getCookie,
} from '@/api/client'

function respondWith(status, data) {
  // Replace the network layer: axios calls the adapter after request interceptors.
  return vi.fn(async (config) => {
    const response = { status, data, headers: {}, config, statusText: String(status) }
    if (status >= 400) {
      const err = new Error(`Request failed with status code ${status}`)
      err.response = response
      err.config = config
      err.isAxiosError = true
      throw err
    }
    return response
  })
}

const clearCookies = () => {
  document.cookie.split('; ').filter(Boolean).forEach((c) => {
    document.cookie = `${c.split('=')[0]}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
  })
}

describe('api client', () => {
  beforeEach(() => clearCookies())
  afterEach(() => onUnauthorized(null))

  it('uses cookies and the /api base URL', () => {
    expect(client.defaults.baseURL).toBe('/api')
    expect(client.defaults.withCredentials).toBe(true)
  })

  it('sends X-CSRFToken from the csrftoken cookie on unsafe requests only', async () => {
    document.cookie = 'csrftoken=abc123; path=/'
    expect(getCookie('csrftoken')).toBe('abc123')
    const adapter = respondWith(200, {})
    await client.post('/auth/logout/', {}, { adapter })
    expect(adapter.mock.calls[0][0].headers['X-CSRFToken']).toBe('abc123')

    await client.get('/auth/me/', { adapter })
    expect(adapter.mock.calls[1][0].headers['X-CSRFToken']).toBeUndefined()
  })

  it('never sends an Authorization token from localStorage', async () => {
    localStorage.setItem('cg_token', 'stale')
    const adapter = respondWith(200, {})
    await client.get('/jobs/', { adapter })
    expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined()
    localStorage.clear()
  })

  it('never forces a JSON content type on FormData (browser adds the multipart boundary)', async () => {
    const adapter = respondWith(201, {})
    const fd = new FormData()
    fd.append('a', '1')
    await client.post('/jobs/', fd, { adapter })
    expect(String(adapter.mock.calls[0][0].headers['Content-Type'] || '')).not.toMatch(/json/)
  })

  it('calls the 401 handler but does not redirect by itself', async () => {
    const handler = vi.fn()
    onUnauthorized(handler)
    const before = window.location.href
    await expect(client.get('/jobs/', { adapter: respondWith(401, {
      error: { message: 'Authentication credentials were not provided.', code: 'not_authenticated', fields: {} },
    }) })).rejects.toThrow()
    expect(handler).toHaveBeenCalledTimes(1)
    expect(window.location.href).toBe(before)
  })

  it('mirrors the envelope message to data.message for legacy views', async () => {
    const err = await client
      .get('/x/', { adapter: respondWith(400, { error: { message: 'Bad', code: 'invalid', fields: {} } }) })
      .catch((e) => e)
    expect(err.response.data.message).toBe('Bad')
  })
})

describe('apiErrorMessage', () => {
  const withData = (status, data) => ({ response: { status, data } })

  it('reads the SPEC §3.5 envelope', () => {
    const err = withData(400, {
      error: { message: 'Invalid username or password.', code: 'invalid', fields: {} },
    })
    expect(apiErrorMessage(err)).toBe('Invalid username or password.')
    expect(apiErrorCode(err)).toBe('invalid')
  })

  it('exposes field errors', () => {
    const fields = { email: ['Enter a valid email address.'] }
    const err = withData(400, { error: { message: 'email: Enter a valid email address.', code: 'invalid', fields } })
    expect(apiFieldErrors(err)).toEqual(fields)
    expect(apiFieldErrors(withData(500, 'oops'))).toEqual({})
  })

  it('falls back for legacy shapes, server errors and network errors', () => {
    expect(apiErrorMessage(withData(400, { message: 'legacy' }))).toBe('legacy')
    expect(apiErrorMessage(withData(403, { detail: 'drf' }))).toBe('drf')
    expect(apiErrorMessage(withData(400, { error: 'str' }))).toBe('str')
    expect(apiErrorMessage(withData(502, '<html>'))).toMatch(/server error/i)
    expect(apiErrorMessage({ message: 'Network Error' })).toMatch(/cannot reach/i)
    expect(apiErrorMessage(withData(400, {}), 'Fallback')).toBe('Fallback')
    expect(apiErrorMessage(null, 'F')).toBe('F')
  })
})
