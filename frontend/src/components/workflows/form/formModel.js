/**
 * Run-form model: defaults, client-side validation (mirrors jobs/submission.py) and the
 * multipart payload for POST /api/jobs/ (SPEC §3.6, §4). Pure functions — unit tested.
 */

export const DISPLAY_TYPES = ['separator', 'info', 'label']
export const FILE_TYPES = ['file', 'local-file']
export const FOLDER_TYPES = ['folder', 'local-folder']
export const TERMS_TYPES = ['terms_checkbox', 'agb_checkbox']
export const TEXT_TYPES = ['text', 'string']
export const MAX_JOB_NAME = 255

export const isDisplay = (p) => DISPLAY_TYPES.includes(p.type)
export const isUpload = (p) => FILE_TYPES.includes(p.type) || FOLDER_TYPES.includes(p.type)
export const isFolder = (p) => FOLDER_TYPES.includes(p.type)
export const isTerms = (p) => TERMS_TYPES.includes(p.type)

/** Parameters that the user can edit (visible, not display-only). */
export const editableParams = (params) => (params || []).filter((p) => !isDisplay(p) && p.visible !== false)

/** Initial form values from the YAML defaults (`value`). */
export function initialValues(params) {
  const values = {}
  for (const p of params || []) {
    if (isDisplay(p)) continue
    if (p.type === 'checkbox') values[p.id] = p.value === true
    else if (isTerms(p)) values[p.id] = false
    else if (isUpload(p)) values[p.id] = []
    else if (p.type === 'number') values[p.id] = p.value === null || p.value === undefined ? '' : String(p.value)
    else values[p.id] = p.value === null || p.value === undefined ? '' : String(p.value)
  }
  return values
}

function acceptExtensions(p) {
  return String(p.accept || '')
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter((t) => t.startsWith('.'))
}

export function fileAccepted(p, filename) {
  const exts = acceptExtensions(p)
  if (!exts.length) return true
  const lower = String(filename).toLowerCase()
  return exts.some((ext) => lower.endsWith(ext))
}

const NUMBER_RE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/

/**
 * Validate values. Returns `{inputId: message}` (empty object when valid).
 * `options.maxUploadMb` limits the total upload size; `options.jobName` is checked too.
 */
export function validate(params, values, options = {}) {
  const errors = {}
  let totalBytes = 0
  for (const p of editableParams(params)) {
    const v = values[p.id]
    if (isUpload(p)) {
      const files = Array.isArray(v) ? v : v ? [v] : []
      if (!files.length) {
        if (p.required) errors[p.id] = isFolder(p) ? 'Please select at least one file.' : 'Please select a file.'
        continue
      }
      if (!isFolder(p) && files.length > 1) {
        errors[p.id] = 'Only one file can be uploaded here.'
        continue
      }
      const bad = files.find((f) => !fileAccepted(p, f.name))
      if (bad) {
        errors[p.id] = `"${bad.name}" is not an accepted file type (${p.accept}).`
        continue
      }
      totalBytes += files.reduce((sum, f) => sum + (f.size || 0), 0)
      continue
    }
    if (p.type === 'checkbox') continue
    if (isTerms(p)) {
      if (p.required !== false && !v) errors[p.id] = 'You must accept this to submit the job.'
      continue
    }
    const text = v === null || v === undefined ? '' : String(v)
    if (!text.trim()) {
      if (p.required) {
        errors[p.id] = ['list', 'radio'].includes(p.type) ? 'Please select a value.' : 'This field is required.'
      }
      continue
    }
    if (p.type === 'number') {
      if (!NUMBER_RE.test(text.trim())) {
        errors[p.id] = 'Please enter a number.'
        continue
      }
      const n = Number(text)
      if (p.min !== null && p.min !== undefined && n < p.min) errors[p.id] = `Must be at least ${p.min}.`
      else if (p.max !== null && p.max !== undefined && n > p.max) errors[p.id] = `Must be at most ${p.max}.`
    } else if (['list', 'radio'].includes(p.type)) {
      if (!(p.values || []).some((o) => o.key === text)) errors[p.id] = 'Select a valid choice.'
    }
  }
  if (options.maxUploadMb && totalBytes > options.maxUploadMb * 1024 * 1024) {
    errors._uploads = `Uploads exceed the maximum total size of ${options.maxUploadMb} MB.`
  }
  if (options.jobName !== undefined && String(options.jobName).trim().length > MAX_JOB_NAME) {
    errors.job_name = `At most ${MAX_JOB_NAME} characters.`
  }
  return errors
}

/**
 * Multipart payload. Checkboxes are always sent (`true`/`false`) so an unchecked box is an
 * explicit value (F4); numbers are sent as typed text and parsed by the server; the job name is
 * sent verbatim (the server trims it; K3).
 */
export function buildFormData(workflowId, jobName, params, values) {
  const fd = new FormData()
  fd.append('workflow', workflowId)
  fd.append('job_name', jobName ?? '')
  for (const p of editableParams(params)) {
    const v = values[p.id]
    if (isUpload(p)) {
      for (const f of Array.isArray(v) ? v : v ? [v] : []) fd.append(p.id, f, f.name)
    } else if (p.type === 'checkbox' || isTerms(p)) {
      fd.append(p.id, v ? 'true' : 'false')
    } else if (v !== null && v !== undefined && String(v) !== '') {
      fd.append(p.id, String(v))
    }
  }
  return fd
}

/** Human-readable size. */
export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let n = Number(bytes)
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }
  return `${i === 0 ? n : n.toFixed(1)} ${units[i]}`
}
