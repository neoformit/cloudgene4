/**
 * Account field rules — a MIRROR of accounts/validation.py (the backend is the source of truth).
 *
 * Both are tested against the same table of examples, accounts/validation_cases.json
 * (see validation.test.js and accounts/tests.py ValidationRulesTest). Change all three together.
 * Each validator returns null when valid, else the same message the server would send in
 * error.fields.
 */

export const MESSAGES = {
  username_required: 'The username is required.',
  username_short: 'The username must contain at least four characters.',
  username_long: 'The username must not contain more than 150 characters.',
  username_chars: 'Your username is not valid. Only characters A-Z, a-z and digits 0-9 are acceptable.',
  email_required: 'E-Mail is required.',
  email_long: 'The e-mail address is too long.',
  email_invalid: 'Please enter a valid mail address.',
  password_required: 'Password is required.',
  password_mismatch: 'Please check your passwords.',
  password_short: 'Password must contain at least six characters!',
  password_long: 'Password must not contain more than 128 characters!',
  password_digit: 'Password must contain at least one number (0-9)!',
  password_lower: 'Password must contain at least one lowercase letter (a-z)!',
  password_upper: 'Password must contain at least one uppercase letter (A-Z)!',
  full_name_required: 'The full name is required.',
  full_name_long: 'The full name must not contain more than 255 characters.',
  group_name_invalid:
    'Group names start with a letter or digit and contain only letters, digits, "_", "-" and "." (max. 80 characters).',
}

const USERNAME_RE = /^[A-Za-z0-9]+$/
const EMAIL_RE = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/
const GROUP_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/

// Python's str.strip() and JS trim() agree for the ASCII/Unicode whitespace users type.
export const normalizeUsername = (value) => (value ?? '').trim()
export const normalizeEmail = (value) => (value ?? '').trim().toLowerCase()

export function validateUsername(value) {
  const v = normalizeUsername(value)
  if (!v) return MESSAGES.username_required
  if (v.length < 4) return MESSAGES.username_short
  if (v.length > 150) return MESSAGES.username_long
  if (!USERNAME_RE.test(v)) return MESSAGES.username_chars
  return null
}

export function validateEmail(value) {
  const v = normalizeEmail(value)
  if (!v) return MESSAGES.email_required
  if (v.length > 254) return MESSAGES.email_long
  if (!EMAIL_RE.test(v)) return MESSAGES.email_invalid
  return null
}

/** `confirm` is compared only when it is not null/undefined. */
export function validatePassword(value, confirm = null) {
  const v = value ?? ''
  if (confirm !== null && confirm !== undefined && v !== confirm) return MESSAGES.password_mismatch
  if (!v) return MESSAGES.password_required
  if (v.length < 6) return MESSAGES.password_short
  if (v.length > 128) return MESSAGES.password_long
  if (!/[0-9]/.test(v)) return MESSAGES.password_digit
  if (!/[a-z]/.test(v)) return MESSAGES.password_lower
  if (!/[A-Z]/.test(v)) return MESSAGES.password_upper
  return null
}

export function validateFullName(value) {
  const v = (value ?? '').trim()
  if (!v) return MESSAGES.full_name_required
  if (v.length > 255) return MESSAGES.full_name_long
  return null
}

export function validateGroupName(value) {
  const v = (value ?? '').trim()
  if (!GROUP_NAME_RE.test(v)) return MESSAGES.group_name_invalid
  return null
}

/**
 * Collect client-side errors: `validateFields({username: [validateUsername, x], ...})`
 * → `{username: 'msg'}` for failing fields only.
 */
export function validateFields(spec) {
  const errors = {}
  for (const [field, [fn, ...args]] of Object.entries(spec)) {
    const message = fn(...args)
    if (message) errors[field] = message
  }
  return errors
}

/** Server `error.fields` ({field: [msg, ...]}) → {field: 'first msg'} for form display. */
export function firstFieldErrors(fields) {
  const out = {}
  for (const [field, messages] of Object.entries(fields || {})) {
    out[field] = Array.isArray(messages) ? messages[0] : String(messages)
  }
  return out
}
