/** API response fixtures shaped like the real backend (jobs/serializers.py, workflows/serializers.py). */

export const workflowFixture = {
  id: 'all-inputs',
  name: 'All Inputs',
  description: 'Every input type',
  version: '1.0.0',
  website: '',
  author: '',
  logo: '',
  category_name: null,
  status: 'enabled',
  public: false,
  definition_errors: [],
  max_upload_mb: 1,
  inputs: [
    { id: 'sep', type: 'separator', label: 'General', value: '', values: [], checkbox_values: null, required: false, visible: true, help: '', details: '', write_file: '', serialize: false, accept: '', min: null, max: null },
    { id: 'info', type: 'info', label: 'Some <b>info</b>', value: '', values: [], checkbox_values: null, required: false, visible: true, help: '', details: '', write_file: '', serialize: false, accept: '', min: null, max: null },
    { id: 'title', type: 'text', label: 'Title', value: 'default text', values: [], checkbox_values: null, required: true, visible: true, help: 'Any text', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'count', type: 'number', label: 'Count', value: 5, values: [], checkbox_values: null, required: true, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: 1, max: 10 },
    { id: 'notes', type: 'textarea', label: 'Notes', value: 'first line', values: [], checkbox_values: null, required: false, visible: true, help: '', details: '', write_file: 'notes.txt', serialize: true, accept: '', min: null, max: null },
    { id: 'choice', type: 'list', label: 'Choice', value: 'b', values: [{ key: 'a', label: 'Alpha' }, { key: 'b', label: 'Beta' }], checkbox_values: null, required: true, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'mode', type: 'radio', label: 'Mode', value: 'fast', values: [{ key: 'fast', label: 'Fast' }, { key: 'accurate', label: 'Accurate' }], checkbox_values: null, required: true, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'flag', type: 'checkbox', label: 'Flag', value: true, values: [], checkbox_values: { true: 'yes', false: 'no' }, required: false, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'data_file', type: 'file', label: 'CSV file', value: null, values: [], checkbox_values: null, required: true, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '.csv', min: null, max: null },
    { id: 'data_folder', type: 'folder', label: 'Folder', value: null, values: [], checkbox_values: null, required: false, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'hidden', type: 'text', label: 'Hidden', value: 'secret', values: [], checkbox_values: null, required: false, visible: false, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'agb', type: 'agb_checkbox', label: 'General terms', value: false, values: [], checkbox_values: null, required: false, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
    { id: 'terms', type: 'terms_checkbox', label: 'I accept', value: false, values: [], checkbox_values: null, required: true, visible: true, help: '', details: '', write_file: '', serialize: true, accept: '', min: null, max: null },
  ],
  outputs: [{ id: 'outdir', type: 'folder', label: 'Output folder', download: true, serialize: true }],
}

const base = {
  id: '3f2b3c1e-0000-4000-8000-000000000001',
  name: 'My run – ünïcode 🚀',
  state: 'running',
  workflow_id: 'hello',
  workflow_name: 'Hello',
  workflow_version: '1.0.0',
  user: 'alice',
  user_id: 2,
  submitted_at: '2026-09-19T10:00:00Z',
  started_at: '2026-09-19T10:00:01Z',
  finished_at: null,
  duration_seconds: 12.5,
  queue_position: null,
  cancel_requested: false,
  expires_at: null,
  purged_at: null,
  can_cancel: true,
  can_delete: false,
  can_restart: false,
}

export const jobListItemFixture = { ...base }

export const jobStatusFixture = {
  ...base,
  updated_at: '2026-09-19T10:00:12Z',
  error_message: '',
  outputs_count: 0,
  steps: [
    {
      id: 7, order: 0, name: 'Say hello', state: 'running', started_at: '2026-09-19T10:00:01Z', finished_at: null,
      processes: [{ name: 'SAY', label: 'Saying', submitted: 3, running: 1, completed: 2, failed: 0, total: 3 }],
    },
  ],
  messages: [
    { id: 1, level: 'info', text: 'Job started.', step: null, created_at: '2026-09-19T10:00:01Z' },
    { id: 2, level: 'warning', text: 'careful', step: 7, created_at: '2026-09-19T10:00:05Z' },
  ],
}

export const jobDetailFixture = {
  ...jobStatusFixture,
  state: 'success',
  finished_at: '2026-09-19T10:01:00Z',
  can_cancel: false,
  can_delete: true,
  outputs_count: 1,
  inputs: [{ id: 'message', label: 'Message', type: 'text', value: 'hi', files: [] }],
  outputs: [
    { id: 11, output_id: 'outdir', label: 'Output folder', name: 'hello.txt', path: 'outdir/hello.txt', size: 3, download_count: 0, url: `/api/jobs/${base.id}/outputs/11/` },
  ],
  log_url: `/api/jobs/${base.id}/log/`,
}
