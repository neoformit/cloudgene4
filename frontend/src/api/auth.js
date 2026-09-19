import client from './client'

// --- Session (T01): GET me → {authenticated, user|null}; login → {user}; logout → {message}
export const me = () =>
  client.get('/auth/me/')

export const login = (username, password) =>
  client.post('/auth/login/', { username, password })

export const logout = () =>
  client.post('/auth/logout/')

// --- Account flows (T04)
export const register = (data) =>
  client.post('/auth/register/', data)

export const getToken = () =>
  client.get('/auth/token/')

export const activate = (activationKey) =>
  client.get(`/auth/activate/${activationKey}/`)

export const requestPasswordReset = (email) =>
  client.post('/auth/password-reset/', { email })

export const confirmPasswordReset = (token, password) =>
  client.post(`/auth/password-reset-confirm/${token}/`, { password })
