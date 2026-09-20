/**
 * src/api/admin.js + src/api/server.js: method, URL and payload of every call (SPEC §3.6).
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import client from '@/api/client'
import * as admin from '@/api/admin'
import * as server from '@/api/server'

let calls
const originalAdapter = client.defaults.adapter

beforeEach(() => {
  calls = []
  client.defaults.adapter = async (config) => {
    calls.push({
      method: config.method,
      url: config.url,
      params: config.params,
      data: config.data ? JSON.parse(config.data) : undefined,
    })
    return { status: 200, data: {}, headers: {}, config, statusText: 'OK' }
  }
})
afterEach(() => {
  client.defaults.adapter = originalAdapter
})

const last = () => calls[calls.length - 1]

describe('admin api', () => {
  const cases = [
    [() => admin.getDashboard(), 'get', '/admin/dashboard/'],
    [() => admin.pauseQueue(), 'post', '/admin/queue/pause/'],
    [() => admin.resumeQueue(), 'post', '/admin/queue/resume/'],
    [() => admin.enterMaintenance('Back soon'), 'post', '/admin/maintenance/enter/', { message: 'Back soon' }],
    [() => admin.exitMaintenance(), 'post', '/admin/maintenance/exit/'],
    [() => admin.getGeneralSettings(), 'get', '/admin/settings/general/'],
    [() => admin.updateGeneralSettings({ name: 'X' }), 'put', '/admin/settings/general/', { name: 'X' }],
    [() => admin.getMailSettings(), 'get', '/admin/settings/mail/'],
    [() => admin.updateMailSettings({ host: 'h' }), 'put', '/admin/settings/mail/', { host: 'h' }],
    [() => admin.sendTestMail('a@b.org'), 'post', '/admin/settings/mail/test/', { to: 'a@b.org' }],
    [() => admin.sendTestMail(), 'post', '/admin/settings/mail/test/', {}],
    [() => admin.getNextflowSettings(), 'get', '/admin/settings/nextflow/'],
    [() => admin.updateNextflowSettings({ profile: 'p' }), 'put', '/admin/settings/nextflow/', { profile: 'p' }],
    [() => admin.getNavbar(), 'get', '/admin/settings/navbar/'],
    [() => admin.updateNavbar([{ title: 'A', url: '/' }]), 'put', '/admin/settings/navbar/', { navbar: [{ title: 'A', url: '/' }] }],
    [() => admin.listPages(), 'get', '/admin/pages/'],
    [() => admin.getPage('about'), 'get', '/admin/pages/about/'],
    [() => admin.savePage('help', '<p>x</p>'), 'put', '/admin/pages/help/', { html: '<p>x</p>' }],
    [() => admin.deletePage('help'), 'delete', '/admin/pages/help/'],
    [() => admin.getPage('../x'), 'get', '/admin/pages/..%2Fx/'],
    [() => admin.listAdminWorkflows(), 'get', '/admin/workflows/'],
    [() => admin.getAdminWorkflow('hello'), 'get', '/admin/workflows/hello/'],
    [() => admin.updateAdminWorkflow('hello', { enabled: false }), 'patch', '/admin/workflows/hello/', { enabled: false }],
    [() => admin.uninstallWorkflow('hello'), 'delete', '/admin/workflows/hello/'],
    [() => admin.reloadWorkflow('hello'), 'post', '/admin/workflows/hello/reload/'],
    [() => admin.installWorkflow({ path: 'p' }), 'post', '/admin/workflows/install/', { path: 'p' }],
    [() => admin.syncWorkflows(), 'post', '/admin/workflows/sync/'],
    [() => admin.getWorkflowNextflow('hello'), 'get', '/admin/workflows/hello/nextflow/'],
    [() => admin.updateWorkflowNextflow('hello', { env: 'A=1' }), 'put', '/admin/workflows/hello/nextflow/', { env: 'A=1' }],
    [() => admin.cancelAdminJob('j1'), 'post', '/admin/jobs/j1/cancel/'],
    [() => admin.restartAdminJob('j1'), 'post', '/admin/jobs/j1/restart/'],
    [() => server.getServerInfo(), 'get', '/server/'],
    [() => server.getPage('about'), 'get', '/pages/about/'],
  ]

  it.each(cases)('%#: request shape', async (fn, method, url, body) => {
    await fn()
    expect(last().method).toBe(method)
    expect(last().url).toBe(url)
    if (body !== undefined) expect(last().data).toEqual(body)
  })

  it('sends only non-empty admin job filters (C6)', async () => {
    await admin.listAdminJobs({ state: 'failed', user: '', workflow: 'hello', page: 2 })
    expect(last().url).toBe('/admin/jobs/')
    expect(last().params).toEqual({ state: 'failed', workflow: 'hello', page: 2 })
  })

  it('sends log filters', async () => {
    await admin.listLogs({ min_level: 'warning', component: '', page: 1 })
    expect(last().url).toBe('/admin/logs/')
    expect(last().params).toEqual({ min_level: 'warning', page: 1 })
  })
})
