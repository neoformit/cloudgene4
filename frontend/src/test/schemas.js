/**
 * JSON Schema definitions for API contract validation
 */

export const userSchema = {
  type: 'object',
  required: ['id', 'username', 'email', 'full_name', 'is_admin'],
  properties: {
    id: { type: 'integer' },
    username: { type: 'string' },
    email: { type: 'string', format: 'email' },
    full_name: { type: 'string' },
    is_admin: { type: 'boolean' }
  }
}

export const authResponseSchema = {
  type: 'object',
  required: ['token', 'user'],
  properties: {
    token: { type: 'string' },
    user: userSchema
  }
}

export const workflowSchema = {
  type: 'object',
  required: ['id', 'name', 'status', 'parameters', 'inputs', 'outputs', 'description', 'version', 'public'],
  properties: {
    id: { type: 'string' },
    name: { type: 'string' },
    status: { type: 'string', enum: ['enabled', 'disabled'] },
    parameters: { type: 'array' },
    inputs: { type: 'array' },
    outputs: { type: 'array' },
    description: { type: 'string' },
    version: { type: 'string' },
    public: { type: 'boolean' },
    allowed_groups: { type: 'array' }
  }
}

export const workflowListSchema = {
  type: 'array',
  items: workflowSchema
}

export const jobSchema = {
  type: 'object',
  required: ['id', 'name', 'status', 'parameters', 'workflow_name', 'user_username', 'submitted_at'],
  properties: {
    id: { type: 'string' },
    name: { type: 'string' },
    status: { type: 'string', enum: ['pending', 'running', 'completed', 'failed', 'cancelled'] },
    parameters: { type: 'object' },
    steps: { type: 'array' },
    messages: { type: 'array' },
    downloads: { type: 'array' },
    can_cancel: { type: 'boolean' },
    can_restart: { type: 'boolean' },
    workflow_name: { type: 'string' },
    user_username: { type: 'string' },
    submitted_at: { type: 'string' }
  }
}

export const jobCreateResponseSchema = {
  type: 'object',
  required: ['id', 'name', 'status', 'parameters', 'workflow_name', 'user_username'],
  properties: {
    id: { type: 'string' },
    name: { type: 'string' },
    status: { type: 'string' },
    parameters: { type: 'object' },
    workflow_name: { type: 'string' },
    user_username: { type: 'string' }
  }
}

export const errorSchema = {
  type: 'object',
  properties: {
    detail: { type: 'string' },
    error: { type: 'string' }
  }
}

export const validationErrorSchema = {
  type: 'object',
  additionalProperties: {
    oneOf: [
      { type: 'string' },
      { type: 'array', items: { type: 'string' } }
    ]
  }
}