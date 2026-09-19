import axios from 'axios'

/**
 * The single HTTP client. Auth is the Django session cookie; every unsafe request
 * carries the CSRF token (Django's `csrftoken` cookie → `X-CSRFToken` header).
 * The cookie is set by the SPA page itself (ensure_csrf_cookie) and rotated on login.
 */
const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})

export function getCookie(name) {
  if (typeof document === 'undefined') return null
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

client.interceptors.request.use((config) => {
  if (config.data instanceof FormData) {
    // Let the browser set multipart/form-data with its boundary
    delete config.headers['Content-Type']
  } else if (config.data && typeof config.data === 'object') {
    config.headers['Content-Type'] = 'application/json'
  }
  // axios only adds the XSRF header for same-origin URLs it can resolve; set it explicitly.
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) {
    const token = getCookie('csrftoken')
    if (token) config.headers['X-CSRFToken'] = token
  }
  return config
})

/**
 * Called on any 401 response. Registered by the router (to reset the auth store and
 * send the user to /login only when the current page needs authentication).
 * Never hard-redirects by itself: anonymous-allowed calls simply reject.
 */
let unauthorizedHandler = null
export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const data = error.response?.data
    // TRANSITIONAL: views not yet migrated read `data.message`; mirror the envelope
    // message there. New code must use apiErrorMessage()/apiFieldErrors().
    if (data && typeof data === 'object' && data.error?.message && data.message === undefined) {
      data.message = data.error.message
    }
    if (error.response?.status === 401 && unauthorizedHandler) {
      unauthorizedHandler(error)
    }
    return Promise.reject(error)
  }
)

/**
 * Human-readable message for any API error (SPEC §3.5 envelope:
 * {"error": {"message", "code", "fields"}}), with fallbacks for legacy shapes and
 * network failures.
 */
export function apiErrorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (!err) return fallback
  const response = err.response
  if (!response) {
    if (err.message === 'Network Error') return 'Cannot reach the server. Check your connection.'
    return err.message || fallback
  }
  const data = response.data
  if (data && typeof data === 'object') {
    if (data.error && typeof data.error === 'object' && data.error.message) {
      return data.error.message
    }
    if (typeof data.error === 'string') return data.error
    if (typeof data.message === 'string') return data.message
    if (typeof data.detail === 'string') return data.detail
  }
  if (response.status >= 500) return 'Server error. Please try again later.'
  return fallback
}

/** `{field: [messages]}` from the envelope (empty object if none). */
export function apiFieldErrors(err) {
  return err?.response?.data?.error?.fields || {}
}

/** Machine-readable error code from the envelope, or null. */
export function apiErrorCode(err) {
  return err?.response?.data?.error?.code || null
}

export default client
