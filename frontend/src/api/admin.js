import client from './client'

/** Admin API (SPEC §3.6). The only place the admin views call the server from. */

// Dashboard & queue
export const getDashboard = () => client.get('/admin/dashboard/')
export const pauseQueue = () => client.post('/admin/queue/pause/')
export const resumeQueue = () => client.post('/admin/queue/resume/')
export const enterMaintenance = (message) =>
  client.post('/admin/maintenance/enter/', message ? { message } : {})
export const exitMaintenance = () => client.post('/admin/maintenance/exit/')

// Settings (settings.yaml sections + global Nextflow files)
export const getGeneralSettings = () => client.get('/admin/settings/general/')
export const updateGeneralSettings = (data) => client.put('/admin/settings/general/', data)
export const getMailSettings = () => client.get('/admin/settings/mail/')
export const updateMailSettings = (data) => client.put('/admin/settings/mail/', data)
export const sendTestMail = (to) => client.post('/admin/settings/mail/test/', to ? { to } : {})
export const getNextflowSettings = () => client.get('/admin/settings/nextflow/')
export const updateNextflowSettings = (data) => client.put('/admin/settings/nextflow/', data)
export const getNavbar = () => client.get('/admin/settings/navbar/')
export const updateNavbar = (navbar) => client.put('/admin/settings/navbar/', { navbar })

// Pages ($CLOUDGENE_HOME/pages/<slug>.html)
export const listPages = () => client.get('/admin/pages/')
export const getPage = (slug) => client.get(`/admin/pages/${encodeURIComponent(slug)}/`)
export const savePage = (slug, html) =>
  client.put(`/admin/pages/${encodeURIComponent(slug)}/`, { html })
export const deletePage = (slug) => client.delete(`/admin/pages/${encodeURIComponent(slug)}/`)

// Workflows (registry)
export const listAdminWorkflows = () => client.get('/admin/workflows/')
export const getAdminWorkflow = (id) => client.get(`/admin/workflows/${id}/`)
export const updateAdminWorkflow = (id, data) => client.patch(`/admin/workflows/${id}/`, data)
export const uninstallWorkflow = (id) => client.delete(`/admin/workflows/${id}/`)
export const reloadWorkflow = (id) => client.post(`/admin/workflows/${id}/reload/`)
export const installWorkflow = (data) => client.post('/admin/workflows/install/', data)
export const syncWorkflows = () => client.post('/admin/workflows/sync/')
export const getWorkflowNextflow = (id) => client.get(`/admin/workflows/${id}/nextflow/`)
export const updateWorkflowNextflow = (id, data) =>
  client.put(`/admin/workflows/${id}/nextflow/`, data)

// Jobs (endpoints implemented by T03; SPEC §3.6)
export const listAdminJobs = (params = {}) => {
  const clean = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== '' && v !== null && v !== undefined) clean[k] = v
  }
  return client.get('/admin/jobs/', { params: clean })
}
export const cancelAdminJob = (id) => client.post(`/admin/jobs/${id}/cancel/`)
export const restartAdminJob = (id) => client.post(`/admin/jobs/${id}/restart/`)

// Logs
export const listLogs = (params = {}) => {
  const clean = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== '' && v !== null && v !== undefined) clean[k] = v
  }
  return client.get('/admin/logs/', { params: clean })
}
