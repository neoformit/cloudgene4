import client from './client'

/** Job states (SPEC §3.3). */
export const JOB_STATES = ['waiting', 'running', 'success', 'failed', 'cancelled']
export const ACTIVE_STATES = ['waiting', 'running']
export const isActiveState = (state) => ACTIVE_STATES.includes(state)

/** GET /api/jobs/?state=&page= — own jobs. Accepts a page number (legacy) or a params object. */
export const listJobs = (params = {}) =>
  client.get('/jobs/', { params: typeof params === 'number' ? { page: params } : params })

export const getJob = (id) => client.get(`/jobs/${id}/`)

/** Light payload for polling (state, steps, messages, queue position). */
export const getJobStatus = (id) => client.get(`/jobs/${id}/status/`)

/** POST /api/jobs/ multipart: workflow, job_name, one field per input id. */
export const submitJob = (formData) => client.post('/jobs/', formData)

export const cancelJob = (id) => client.post(`/jobs/${id}/cancel/`)

export const deleteJob = (id) => client.delete(`/jobs/${id}/`)

/** Plain-text log. */
export const getJobLog = (id) =>
  client.get(`/jobs/${id}/log/`, { responseType: 'text', transformResponse: [(d) => d] })

/** Same-origin URLs usable in <a href> (session cookie auth). */
export const jobLogUrl = (id) => `/api/jobs/${id}/log/`
export const jobOutputUrl = (jobId, fileId) => `/api/jobs/${jobId}/outputs/${fileId}/`

// -- Admin (SPEC §3.6) ---------------------------------------------------------------------
/** GET /api/admin/jobs/?state=&user=&workflow=&search=&page= */
export const adminListJobs = (params = {}) => client.get('/admin/jobs/', { params })
export const adminCancelJob = (id) => client.post(`/admin/jobs/${id}/cancel/`)
export const adminRestartJob = (id) => client.post(`/admin/jobs/${id}/restart/`)
/** @deprecated use adminRestartJob */
export const restartJob = adminRestartJob
