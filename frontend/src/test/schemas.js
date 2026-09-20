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

// POST /api/auth/login → {user}   (session cookie; no token — SPEC §3.4)
export const authResponseSchema = {
  type: 'object',
  required: ['user'],
  additionalProperties: false,
  properties: {
    user: userSchema
  }
}

// GET /api/auth/me → {authenticated, user|null}
export const meResponseSchema = {
  type: 'object',
  required: ['authenticated', 'user'],
  properties: {
    authenticated: { type: 'boolean' },
    user: { oneOf: [{ type: 'null' }, userSchema] }
  }
}

// --- Accounts (T04): groups are a list of names
const accountUserProps = {
  ...userSchema.properties,
  is_active: { type: 'boolean' },
  groups: { type: 'array', items: { type: 'string' } },
  date_joined: { type: 'string', format: 'date-time' },
  last_login: { type: ['string', 'null'] },
}

// GET/PATCH /api/me → user + api_token metadata (never the key)
export const profileSchema = {
  type: 'object',
  required: [...userSchema.required, 'groups', 'api_token'],
  properties: {
    ...accountUserProps,
    api_token: {
      oneOf: [
        { type: 'null' },
        {
          type: 'object',
          required: ['created'],
          additionalProperties: false,
          properties: { created: { type: 'string', format: 'date-time' } },
        },
      ],
    },
  },
}

// POST /api/me/token → {token, created}
export const apiTokenSchema = {
  type: 'object',
  required: ['token', 'created'],
  properties: { token: { type: 'string' }, created: { type: 'string', format: 'date-time' } },
}

// GET /api/admin/users → paginated
export const adminUserListSchema = {
  type: 'object',
  required: ['count', 'results'],
  properties: {
    count: { type: 'integer' },
    results: {
      type: 'array',
      items: {
        type: 'object',
        required: [...userSchema.required, 'groups', 'is_active', 'is_superuser'],
        properties: { ...accountUserProps, is_superuser: { type: 'boolean' } },
      },
    },
  },
}

// GET /api/admin/groups → plain array
export const adminGroupListSchema = {
  type: 'array',
  items: {
    type: 'object',
    required: ['id', 'name', 'member_count'],
    properties: { id: { type: 'integer' }, name: { type: 'string' }, member_count: { type: 'integer' } },
  },
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

// Error envelope for every API error (SPEC §3.5)
export const errorSchema = {
  type: 'object',
  required: ['error'],
  additionalProperties: false,
  properties: {
    error: {
      type: 'object',
      required: ['message', 'code', 'fields'],
      properties: {
        message: { type: 'string', minLength: 1 },
        code: { type: 'string' },
        fields: {
          type: 'object',
          additionalProperties: { type: 'array', items: { type: 'string' } }
        }
      }
    }
  }
}

// Validation errors use the same envelope; field messages are in error.fields
export const validationErrorSchema = errorSchema
