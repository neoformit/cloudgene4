/**
 * Contract tests for workflows API endpoints
 * 
 * These tests validate that the frontend API client correctly handles
 * workflow listing and detail responses from the backend.
 */

import { describe, it, expect, beforeAll, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as workflowsApi from '@/api/workflows'
import { workflowSchema, workflowListSchema } from '../schemas'

// Mock the HTTP client to avoid real network requests
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn()
  }
}))

const ajv = new Ajv()
addFormats(ajv)
global.ajv = ajv

describe('Workflows API Contracts', () => {
  beforeAll(() => {
    vi.clearAllMocks()
  })

  describe('Workflow Listing Contract', () => {
    it('should handle successful workflow list retrieval', async () => {
      const mockResponse = {
        data: [
          {
            id: 'workflow-1',
            name: 'Test Workflow 1',
            status: 'enabled',
            parameters: [
              {
                id: 'param1',
                name: 'Parameter 1',
                parameter_type: 'text',
                required: true,
                is_input: true,
                is_output: false
              }
            ],
            inputs: [
              {
                id: 'param1',
                name: 'Parameter 1',
                parameter_type: 'text',
                required: true
              }
            ],
            outputs: [],
            description: 'A test workflow',
            version: '1.0.0',
            public: true,
            allowed_groups: []
          },
          {
            id: 'workflow-2',
            name: 'Test Workflow 2',
            status: 'enabled',
            parameters: [],
            inputs: [],
            outputs: [
              {
                id: 'output1',
                name: 'Output 1',
                parameter_type: 'file'
              }
            ],
            description: 'Another test workflow',
            version: '2.0.0',
            public: false,
            allowed_groups: ['group1']
          }
        ]
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.listWorkflows()

      expect(client.default.get).toHaveBeenCalledWith('/workflows/')
      expect(response.data).toMatchApiSchema(workflowListSchema)
      
      // Verify each workflow has proper structure
      response.data.forEach(workflow => {
        expect(workflow).toMatchApiSchema(workflowSchema)
        expect(workflow.inputs).toEqual(expect.any(Array))
        expect(workflow.outputs).toEqual(expect.any(Array))
      })
    })

    it('should handle empty workflow list', async () => {
      const mockResponse = {
        data: []
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.listWorkflows()

      expect(response.data).toEqual([])
      expect(response.data).toMatchApiSchema(workflowListSchema)
    })

    it('should handle paginated workflow list', async () => {
      const mockResponse = {
        data: {
          results: [
            {
              id: 'workflow-1',
              name: 'Paginated Workflow',
              status: 'enabled',
              parameters: [],
              inputs: [],
              outputs: [],
              description: 'A paginated workflow',
              version: '1.0.0',
              public: true,
              allowed_groups: []
            }
          ],
          count: 1,
          next: null,
          previous: null
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.listWorkflows()

      expect(response.data).toHaveApiField('results')
      expect(response.data).toHaveApiField('count')
      expect(response.data.results).toEqual(expect.any(Array))
      
      if (response.data.results.length > 0) {
        expect(response.data.results[0]).toMatchApiSchema(workflowSchema)
      }
    })
  })

  describe('Workflow Detail Contract', () => {
    it('should handle successful workflow detail retrieval', async () => {
      const mockResponse = {
        data: {
          id: 'detailed-workflow',
          name: 'Detailed Test Workflow',
          status: 'enabled',
          parameters: [
            {
              id: 'input_param',
              name: 'Input Parameter',
              parameter_type: 'text',
              required: true,
              is_input: true,
              is_output: false,
              order: 1,
              description: 'A required input parameter'
            },
            {
              id: 'output_param',
              name: 'Output Parameter',
              parameter_type: 'file',
              required: false,
              is_input: false,
              is_output: true,
              order: 2,
              description: 'An output file parameter'
            }
          ],
          inputs: [
            {
              id: 'input_param',
              name: 'Input Parameter',
              parameter_type: 'text',
              required: true,
              description: 'A required input parameter'
            }
          ],
          outputs: [
            {
              id: 'output_param',
              name: 'Output Parameter',
              parameter_type: 'file',
              description: 'An output file parameter'
            }
          ],
          description: 'A detailed workflow with comprehensive parameters',
          version: '2.1.0',
          public: false,
          allowed_groups: ['research-group', 'admin-group']
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.getWorkflow('detailed-workflow')

      expect(client.default.get).toHaveBeenCalledWith('/workflows/detailed-workflow/')
      expect(response.data).toMatchApiSchema(workflowSchema)
      
      // Verify inputs/outputs separation
      expect(response.data.inputs).toEqual(expect.any(Array))
      expect(response.data.outputs).toEqual(expect.any(Array))
      
      // Verify inputs contain only input parameters
      response.data.inputs.forEach(input => {
        expect(input).toHaveApiField('id')
        expect(input).toHaveApiField('name')
        expect(input).toHaveApiField('parameter_type')
      })
      
      // Verify outputs contain only output parameters
      response.data.outputs.forEach(output => {
        expect(output).toHaveApiField('id')
        expect(output).toHaveApiField('name')
        expect(output).toHaveApiField('parameter_type')
      })
    })

    it('should handle workflow not found error', async () => {
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
        await workflowsApi.getWorkflow('nonexistent-workflow')
        expect.fail('Expected workflow retrieval to throw error')
      } catch (error) {
        expect(error.response.status).toBe(404)
        expect(error.response.data).toHaveApiField('detail')
      }
    })

    it('should handle workflow access denied error', async () => {
      const mockError = {
        response: {
          status: 404, // Backend returns 404 instead of 403 for security
          data: {
            detail: 'Not found.'
          }
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockRejectedValue(mockError)

      try {
        await workflowsApi.getWorkflow('private-workflow')
        expect.fail('Expected workflow retrieval to throw error')
      } catch (error) {
        expect(error.response.status).toBe(404)
        expect(error.response.data).toHaveApiField('detail')
      }
    })
  })

  describe('Categories Contract', () => {
    it('should handle successful categories list retrieval', async () => {
      const mockResponse = {
        data: [
          {
            id: 1,
            name: 'Bioinformatics',
            description: 'Biological data analysis workflows'
          },
          {
            id: 2,
            name: 'Machine Learning',
            description: 'ML and AI workflows'
          }
        ]
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.listCategories()

      expect(client.default.get).toHaveBeenCalledWith('/categories/')
      expect(response.data).toEqual(expect.any(Array))
      
      response.data.forEach(category => {
        expect(category).toHaveApiField('id')
        expect(category).toHaveApiField('name')
        expect(category).toHaveApiField('description')
      })
    })

    it('should handle empty categories list', async () => {
      const mockResponse = {
        data: []
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.listCategories()

      expect(response.data).toEqual([])
    })
  })

  describe('Workflow Structure Validation', () => {
    it('should ensure inputs and outputs are properly separated', async () => {
      const mockResponse = {
        data: {
          id: 'separation-test-workflow',
          name: 'Input/Output Separation Test',
          status: 'enabled',
          parameters: [
            { id: 'input1', is_input: true, is_output: false },
            { id: 'input2', is_input: true, is_output: false },
            { id: 'output1', is_input: false, is_output: true },
            { id: 'both', is_input: true, is_output: true }  // Edge case
          ],
          inputs: [
            { id: 'input1' },
            { id: 'input2' },
            { id: 'both' }
          ],
          outputs: [
            { id: 'output1' },
            { id: 'both' }
          ],
          description: 'Test workflow',
          version: '1.0.0',
          public: true,
          allowed_groups: []
        }
      }

      const client = await import('@/api/client')
      client.default.get.mockResolvedValue(mockResponse)

      const response = await workflowsApi.getWorkflow('separation-test-workflow')

      const data = response.data
      
      // Verify proper separation
      const inputIds = data.inputs.map(i => i.id)
      const outputIds = data.outputs.map(o => o.id)
      
      expect(inputIds).toContain('input1')
      expect(inputIds).toContain('input2')
      expect(inputIds).toContain('both')
      expect(inputIds).not.toContain('output1')
      
      expect(outputIds).toContain('output1')
      expect(outputIds).toContain('both')
      expect(outputIds).not.toContain('input1')
      expect(outputIds).not.toContain('input2')
    })
  })
})