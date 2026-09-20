/**
 * Jobs API module (src/api/jobs.js): endpoints, payloads and response fixtures (SPEC §3.6).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as jobsApi from '@/api/jobs'
import { jobSchema, jobStatusSchema, jobListItemSchema, validationErrorSchema } from '../schemas'
import { jobDetailFixture, jobStatusFixture, jobListItemFixture } from '../fixtures/jobs'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

const ajv = new Ajv({ allowUnionTypes: true, strict: false })
addFormats(ajv)
global.ajv = ajv

let client
beforeEach(async () => {
  client = (await import('@/api/client')).default
  vi.clearAllMocks()
})

describe('jobs api endpoints', () => {
  it('lists own jobs with params or a page number', async () => {
    client.get.mockResolvedValue({ data: { count: 1, next: null, previous: null, results: [jobListItemFixture] } })
    await jobsApi.listJobs({ state: 'running', page: 2 })
    expect(client.get).toHaveBeenCalledWith('/jobs/', { params: { state: 'running', page: 2 } })
    await jobsApi.listJobs(3)
    expect(client.get).toHaveBeenLastCalledWith('/jobs/', { params: { page: 3 } })
  })

  it('uses the SPEC paths for detail, status, cancel, delete, log', async () => {
    client.get.mockResolvedValue({ data: {} })
    client.post.mockResolvedValue({ data: {} })
    client.delete.mockResolvedValue({ data: null })
    await jobsApi.getJob('abc')
    expect(client.get).toHaveBeenCalledWith('/jobs/abc/')
    await jobsApi.getJobStatus('abc')
    expect(client.get).toHaveBeenLastCalledWith('/jobs/abc/status/')
    await jobsApi.cancelJob('abc')
    expect(client.post).toHaveBeenCalledWith('/jobs/abc/cancel/')
    await jobsApi.deleteJob('abc')
    expect(client.delete).toHaveBeenCalledWith('/jobs/abc/')
    await jobsApi.getJobLog('abc')
    expect(client.get.mock.calls.at(-1)[0]).toBe('/jobs/abc/log/')
    expect(client.get.mock.calls.at(-1)[1].responseType).toBe('text')
    expect(jobsApi.jobLogUrl('abc')).toBe('/api/jobs/abc/log/')
    expect(jobsApi.jobOutputUrl('abc', 5)).toBe('/api/jobs/abc/outputs/5/')
  })

  it('submits multipart FormData unchanged', async () => {
    client.post.mockResolvedValue({ data: jobDetailFixture })
    const fd = new FormData()
    fd.append('workflow', 'hello')
    fd.append('job_name', 'a b')
    const res = await jobsApi.submitJob(fd)
    expect(client.post).toHaveBeenCalledWith('/jobs/', fd)
    expect(res.data).toMatchApiSchema(jobSchema)
  })

  it('admin endpoints', async () => {
    client.get.mockResolvedValue({ data: {} })
    client.post.mockResolvedValue({ data: {} })
    await jobsApi.adminListJobs({ state: 'failed', user: 'bob' })
    expect(client.get).toHaveBeenCalledWith('/admin/jobs/', { params: { state: 'failed', user: 'bob' } })
    await jobsApi.adminCancelJob('x')
    expect(client.post).toHaveBeenCalledWith('/admin/jobs/x/cancel/')
    await jobsApi.adminRestartJob('x')
    expect(client.post).toHaveBeenLastCalledWith('/admin/jobs/x/restart/')
  })

  it('state helpers', () => {
    expect(jobsApi.JOB_STATES).toEqual(['waiting', 'running', 'success', 'failed', 'cancelled'])
    expect(jobsApi.isActiveState('waiting')).toBe(true)
    expect(jobsApi.isActiveState('success')).toBe(false)
  })
})

describe('job response fixtures match the contract', () => {
  it('list item / status / detail', () => {
    expect(jobListItemFixture).toMatchApiSchema(jobListItemSchema)
    expect(jobStatusFixture).toMatchApiSchema(jobStatusSchema)
    expect(jobDetailFixture).toMatchApiSchema(jobSchema)
  })

  it('rejects legacy shapes (F1–F3)', () => {
    const legacy = { ...jobListItemFixture, state: 'completed' }
    expect(ajv.compile(jobListItemSchema)(legacy)).toBe(false)
    const { state, ...noState } = jobListItemFixture
    expect(ajv.compile(jobListItemSchema)({ ...noState, status: state })).toBe(false)
  })

  it('field errors use the envelope', () => {
    const err = { error: { message: 'count: Must be at most 10.', code: 'invalid', fields: { count: ['Must be at most 10.'] } } }
    expect(err).toMatchApiSchema(validationErrorSchema)
  })
})
