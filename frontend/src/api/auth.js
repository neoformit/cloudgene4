import client from './client'

// --- Session (T01): GET me → {authenticated, user|null}; login → {user}; logout → {message}
// Login errors: 400 invalid_credentials, 403 account_inactive, 429 account_locked (SPEC §3.4).
export const me = () =>
  client.get('/auth/me/')

export const login = (username, password) =>
  client.post('/auth/login/', { username, password })

export const logout = () =>
  client.post('/auth/logout/')

// --- Account flows (T04)
/** → 201 {user, message, activation_required}; field errors in error.fields */
export const register = (data) =>
  client.post('/auth/register/', data)

/** → 200 {status: 'activated'|'already_active', message}; 400 invalid_activation_key */
export const activate = (activationKey) =>
  client.post(`/auth/activate/${encodeURIComponent(activationKey)}/`)

/** Always 200 {message} (does not reveal whether the address is registered). */
export const requestPasswordReset = (email) =>
  client.post('/auth/password-reset/', { email })

/** → 200 {message}; 400 invalid_token | expired_token | field error `password` */
export const confirmPasswordReset = (token, password, passwordConfirm) => {
  const body = { password }
  if (passwordConfirm !== undefined) body.password_confirm = passwordConfirm
  return client.post(`/auth/password-reset/${encodeURIComponent(token)}/`, body)
}
