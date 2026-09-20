import client from './client'

// --- Own profile (SPEC §3.6 "Profile")
/** GET /me/ → user + api_token: {created}|null (the key itself is never returned here) */
export const getProfile = () =>
  client.get('/me/')

/** PATCH /me/ {full_name?, email?, password?, password_confirm?, current_password?}
 *  (current_password is required when changing e-mail or password) */
export const updateProfile = (data) =>
  client.patch('/me/', data)

/** DELETE /me/ {password} — deletes the account and ends the session */
export const deleteAccount = (password) =>
  client.delete('/me/', { data: { password } })

/** POST /me/token/ → 201 {token, created}; replaces any existing token. Shown once. */
export const createApiToken = () =>
  client.post('/me/token/')

export const revokeApiToken = () =>
  client.delete('/me/token/')

// --- Admin: users (paginated {count, next, previous, results})
/** params: {search, group, is_active, page, page_size} */
export const listUsers = (params = {}) =>
  client.get('/admin/users/', { params })

export const getUser = (id) =>
  client.get(`/admin/users/${id}/`)

/** PATCH {groups: [names] (the admin group is ignored here), is_active, is_admin} */
export const updateUser = (id, data) =>
  client.patch(`/admin/users/${id}/`, data)

export const deleteUser = (id) =>
  client.delete(`/admin/users/${id}/`)

// --- Admin: groups (plain array [{id, name, member_count}], not paginated)
export const listGroups = () =>
  client.get('/admin/groups/')

export const createGroup = (data) =>
  client.post('/admin/groups/', data)

export const deleteGroup = (id) =>
  client.delete(`/admin/groups/${id}/`)
