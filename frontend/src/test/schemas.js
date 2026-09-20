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

// GET /api/workflows/{id} (SPEC §3.6, §4) — inputs/outputs from the parsed cloudgene.yaml
export const workflowInputSchema = {
  type: 'object',
  required: ['id', 'type', 'label', 'value', 'values', 'required', 'visible', 'help', 'details',
    'accept', 'min', 'max', 'write_file', 'serialize', 'checkbox_values'],
  properties: {
    id: { type: 'string' },
    type: {
      type: 'string',
      enum: ['text', 'string', 'number', 'textarea', 'list', 'radio', 'checkbox', 'file', 'folder',
        'local-file', 'local-folder', 'separator', 'info', 'label', 'terms_checkbox', 'agb_checkbox'],
    },
    label: { type: 'string' },
    values: {
      type: 'array',
      items: { type: 'object', required: ['key', 'label'], properties: { key: { type: 'string' }, label: { type: 'string' } } },
    },
    required: { type: 'boolean' },
    visible: { type: 'boolean' },
    min: { type: ['number', 'null'] },
    max: { type: ['number', 'null'] },
    checkbox_values: { type: ['object', 'null'] },
  },
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
  required: ['id', 'name', 'version', 'description', 'status', 'public', 'inputs', 'outputs',
    'definition_errors', 'max_upload_mb'],
  properties: {
    id: { type: 'string' },
    name: { type: 'string' },
    version: { type: 'string' },
    description: { type: 'string' },
    status: { type: 'string' },
    public: { type: 'boolean' },
    inputs: { type: 'array', items: workflowInputSchema },
    outputs: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'type', 'label', 'download', 'serialize'],
      },
    },
    definition_errors: { type: 'array', items: { type: 'string' } },
    max_upload_mb: { type: 'integer' },
  },
}

export const workflowListSchema = {
  type: 'array',
  items: workflowSchema,
}

const JOB_STATE = { type: 'string', enum: ['waiting', 'running', 'success', 'failed', 'cancelled'] }

// GET /api/jobs/ items (JobListSerializer)
export const jobListItemSchema = {
  type: 'object',
  required: ['id', 'name', 'state', 'workflow_id', 'workflow_name', 'workflow_version', 'user',
    'submitted_at', 'started_at', 'finished_at', 'duration_seconds', 'queue_position',
    'cancel_requested', 'expires_at', 'can_cancel', 'can_delete', 'can_restart'],
  properties: {
    id: { type: 'string' },
    name: { type: 'string' },
    state: JOB_STATE,
    queue_position: { type: ['integer', 'null'] },
    can_cancel: { type: 'boolean' },
    can_delete: { type: 'boolean' },
  },
}

// GET /api/jobs/{id}/status/
export const jobStatusSchema = {
  type: 'object',
  required: [...jobListItemSchema.required, 'updated_at', 'error_message', 'steps', 'messages', 'outputs_count'],
  properties: {
    ...jobListItemSchema.properties,
    steps: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'order', 'name', 'state', 'processes'],
        properties: {
          processes: {
            type: 'array',
            items: {
              type: 'object',
              required: ['name', 'label', 'submitted', 'running', 'completed', 'failed', 'total'],
            },
          },
        },
      },
    },
    messages: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'level', 'text', 'step', 'created_at'],
        properties: { level: { type: 'string', enum: ['debug', 'info', 'success', 'warning', 'error'] } },
      },
    },
  },
}

// GET /api/jobs/{id}/ and POST /api/jobs/ (201)
export const jobSchema = {
  type: 'object',
  required: [...jobStatusSchema.required, 'inputs', 'outputs', 'log_url'],
  properties: {
    ...jobStatusSchema.properties,
    inputs: {
      type: 'array',
      items: { type: 'object', required: ['id', 'label', 'type', 'value', 'files'] },
    },
    outputs: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'output_id', 'label', 'name', 'path', 'size', 'download_count', 'url'],
      },
    },
  },
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
