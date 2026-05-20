/**
 * Contract tests for jobs API endpoints
 * 
 * These tests validate that the frontend API client correctly handles
 * job submission, retrieval, and management responses from the backend.
 */

import { describe, it, expect, beforeAll, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as jobsApi from '@/api/jobs'
import { jobSchema, jobCreateResponseSchema, validationErrorSchema } from '../schemas'

// Mock the HTTP client to avoid real network requests
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn()
  }
}))

const ajv = new Ajv()
addFormats(ajv)
global.ajv = ajv

describe('Jobs API Contracts', () => {
  beforeAll(() => {
    vi.clearAllMocks()
  })

  describe('Job Submission Contract', () => {
    it('should handle successful JSON job submission', async () => {
      const mockResponse = {
        data: {
          id: 'job-123',
          name: 'test-job',
          status: 'pending',
          parameters: { input_param: 'value' },
          workflow_name: 'Test Workflow',
          user_username: 'testuser'
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const jobData = {
        workflow_id: 'test-workflow',
        name: 'test-job',
        parameters: { input_param: 'value' }
      }

      const response = await jobsApi.submitJob(jobData)

      expect(client.default.post).toHaveBeenCalledWith('/jobs/', jobData)
      expect(response.data).toMatchApiSchema(jobCreateResponseSchema)
    })

    it('should handle successful FormData job submission', async () => {
      const mockResponse = {
        data: {
          id: 'job-456',
          name: 'formdata-job',
          status: 'pending',
          parameters: { file_param: 'uploaded_file.txt' },
          workflow_name: 'File Workflow',
          user_username: 'testuser'
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const formData = new FormData()
      formData.append('workflow_id', 'test-workflow')
      formData.append('job_name', 'formdata-job')
      formData.append('file_param', new File(['content'], 'test.txt'))

      const response = await jobsApi.submitJob(formData)

      expect(client.default.post).toHaveBeenCalledWith('/jobs/', formData)
      expect(response.data).toMatchApiSchema(jobCreateResponseSchema)
    })

    it('should handle job submission validation errors', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            workflow_id: ['This field is required.'],
            parameters: ['Required parameter "input_param" is missing.']
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await jobsApi.submitJob({ name: 'incomplete-job' })
        expect.fail('Expected job submission to throw error')
      } catch (error) {
        expect(error.response.status).toBe(400)
        expect(error.response.data).toMatchApiSchema(validationErrorSchema)
        expect(error.response.data).toHaveApiField('workflow_id')
        expect(error.response.data).toHaveApiField('parameters')
      }
    })

    it('should handle unknown workflow error', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            workflow_id: ['Workflow does not exist or you do not have permission to access it.']
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await jobsApi.submitJob({
          workflow_id: 'nonexistent-workflow',
          name: 'test-job',
          parameters: {}
        })
        expect.fail('Expected job submission to throw error')
      } catch (error) {
        expect(error.response.status).toBe(400)
        expect(error.response.data).toHaveApiField('workflow_id')
      }
    })
  })

  describe('Job Retrieval Contract', () => {
    it('should handle successful job detail retrieval', async () => {
      const mockResponse = {
        data: {
          id: 'job-123',
          name: 'test-job',
          status: 'completed',
          parameters: { input_param: 'value' },
          steps: [
            { name: 'Step 1', status: 'completed' },
            { name: 'Step 2', status: 'completed' }
          ],
          messages: [
            { level: 'info', message: 'Job started' },
            { level: 'info', message: 'Job completed' }
          ],
          downloads: [
            { name: 'output.txt', url: '/download/output.txt' }
          ],
          can_cancel: false,
          can_restart: true,
          workflow_name: 'Test Workflow',
          user_username: 'testuser',
          submitted_at: '2023-01-01T12:00:00Z'
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await jobsApi.getJob('job-123')

      expect(client.default.get).toHaveBeenCalledWith('/jobs/job-123/')
      expect(response.data).toMatchApiSchema(jobSchema)
    })

    it('should handle job not found error', async () => {
      const mockError = {
        response: {
          status: 404,
          data: {
            detail: 'Not found.'
          }
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockRejectedValue(mockError)

      try {
        await jobsApi.getJob('nonexistent-job')
        expect.fail('Expected job retrieval to throw error')
      } catch (error) {
        expect(error.response.status).toBe(404)
        expect(error.response.data).toHaveApiField('detail')
      }
    })

    it('should handle job list retrieval', async () => {
      const mockResponse = {
        data: {
          results: [
            {
              id: 'job-1',
              name: 'job-1',
              status: 'pending',
              parameters: {},
              steps: [],
              messages: [],
              downloads: [],
              can_cancel: true,
              can_restart: false,
              workflow_name: 'Workflow 1',
              user_username: 'user1',
              submitted_at: '2023-01-01T12:00:00Z'
            }
          ],
          count: 1,
          next: null,
          previous: null
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await jobsApi.listJobs(1)

      expect(client.default.get).toHaveBeenCalledWith('/jobs/', { params: { page: 1 } })
      expect(response.data).toHaveApiField('results')
      expect(response.data.results).toEqual(expect.any(Array))
      
      if (response.data.results.length > 0) {
        expect(response.data.results[0]).toMatchApiSchema(jobSchema)
      }
    })
  })

  describe('Job Actions Contract', () => {
    it('should handle successful job cancellation', async () => {
      const mockResponse = {
        data: { message: 'Job cancelled successfully.' }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const response = await jobsApi.cancelJob('job-123')

      expect(client.default.post).toHaveBeenCalledWith('/jobs/job-123/cancel/')
      expect(response.data).toHaveApiField('message')
    })

    it('should handle job cancellation permission error', async () => {
      const mockError = {
        response: {
          status: 403,
          data: {
            detail: 'You do not have permission to perform this action.'
          }
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockRejectedValue(mockError)

      try {
        await jobsApi.cancelJob('other-users-job')
        expect.fail('Expected job cancellation to throw error')
      } catch (error) {
        expect(error.response.status).toBe(403)
        expect(error.response.data).toHaveApiField('detail')
      }
    })

    it('should handle successful job restart', async () => {
      const mockResponse = {
        data: { 
          message: 'Job restarted successfully.',
          new_job_id: 'job-456'
        }
      }

      const client = await import('@/api/client')
      client.default.post.mockResolvedValue(mockResponse)

      const response = await jobsApi.restartJob('job-123')

      expect(client.default.post).toHaveBeenCalledWith('/jobs/job-123/restart/')
      expect(response.data).toHaveApiField('message')
    })
  })

  describe('Job Logs Contract', () => {
    it('should handle successful job logs retrieval', async () => {
      const mockResponse = {
        data: {
          logs: [
            { timestamp: '2023-01-01T12:00:00Z', level: 'info', message: 'Starting job' },
            { timestamp: '2023-01-01T12:05:00Z', level: 'info', message: 'Job completed' }
          ]
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await jobsApi.getJobLogs('job-123')

      expect(client.default.get).toHaveBeenCalledWith('/jobs/job-123/logs/')
      expect(response.data).toHaveApiField('logs')
      expect(response.data.logs).toEqual(expect.any(Array))
    })
  })

  describe('Downloads Contract', () => {
    it('should handle successful downloads listing', async () => {
      const mockResponse = {
        data: [
          {
            name: 'output.txt',
            size: 1024,
            url: '/api/jobs/job-123/download/output.txt',
            type: 'output'
          }
        ]
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await jobsApi.listDownloads('job-123')

      expect(client.default.get).toHaveBeenCalledWith('/jobs/job-123/download/')
      expect(response.data).toEqual(expect.any(Array))
    })
  })
})