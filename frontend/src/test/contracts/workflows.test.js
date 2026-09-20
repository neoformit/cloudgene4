/**
 * Workflows API module (public endpoints) and the run-form schema contract (SPEC §4).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import * as workflowsApi from '@/api/workflows'
import { workflowSchema, workflowListSchema } from '../schemas'
import { workflowFixture } from '../fixtures/jobs'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

const ajv = new Ajv({ allowUnionTypes: true, strict: false })
addFormats(ajv)
global.ajv = ajv

let client
beforeEach(async () => {
  client = (await import('@/api/client')).default
  vi.clearAllMocks()
})

describe('workflows api', () => {
  it('lists and gets workflows', async () => {
    client.get.mockResolvedValue({ data: [workflowFixture] })
    const res = await workflowsApi.listWorkflows()
    expect(client.get).toHaveBeenCalledWith('/workflows/')
    expect(res.data).toMatchApiSchema(workflowListSchema)
    client.get.mockResolvedValue({ data: workflowFixture })
    const one = await workflowsApi.getWorkflow('all-inputs')
    expect(client.get).toHaveBeenLastCalledWith('/workflows/all-inputs/')
    expect(one.data).toMatchApiSchema(workflowSchema)
  })

  it('rejects the legacy parameter shape (W2)', () => {
    const legacy = { ...workflowFixture, inputs: [{ id: 'x', name: 'X', parameter_type: 'text', required: true }] }
    expect(ajv.compile(workflowSchema)(legacy)).toBe(false)
  })

  it('rejects unknown input types', () => {
    const bad = { ...workflowFixture, inputs: [{ ...workflowFixture.inputs[2], type: 'app_list' }] }
    expect(ajv.compile(workflowSchema)(bad)).toBe(false)
  })
})
