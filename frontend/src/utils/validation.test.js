/**
 * The frontend rules must agree with the backend (accounts/validation.py, the source of truth).
 * Both suites run the same table: accounts/validation_cases.json.
 */
import { describe, it, expect } from 'vitest'
import {
  firstFieldErrors,
  normalizeEmail,
  normalizeUsername,
  validateEmail,
  validateFields,
  validateFullName,
  validateGroupName,
  validatePassword,
  validateUsername,
} from './validation'
// The backend's table (the repo root is two levels above frontend/src).
import CASES from '../../../accounts/validation_cases.json'


describe('validation mirrors accounts/validation.py', () => {
  it.each(CASES.username)('username %j → %j', (value, expected) => {
    expect(validateUsername(value)).toBe(expected)
  })
  it.each(CASES.email)('email %j → %j', (value, expected) => {
    expect(validateEmail(value)).toBe(expected)
  })
  it.each(CASES.password)('password %j (confirm %j) → %j', (value, confirm, expected) => {
    expect(validatePassword(value, confirm)).toBe(expected)
  })
  it.each(CASES.full_name)('full name %j → %j', (value, expected) => {
    expect(validateFullName(value)).toBe(expected)
  })
  it.each(CASES.group_name)('group name %j → %j', (value, expected) => {
    expect(validateGroupName(value)).toBe(expected)
  })
})

describe('helpers', () => {
  it('normalises like the backend model', () => {
    expect(normalizeEmail('  Bob@Example.ORG ')).toBe('bob@example.org')
    expect(normalizeUsername('  Bob ')).toBe('Bob')
  })

  it('validateFields collects only failures', () => {
    expect(
      validateFields({ username: [validateUsername, 'ab'], email: [validateEmail, 'a@b.org'] })
    ).toEqual({ username: 'The username must contain at least four characters.' })
  })

  it('firstFieldErrors takes the first server message per field', () => {
    expect(firstFieldErrors({ email: ['taken', 'other'], name: 'x' })).toEqual({ email: 'taken', name: 'x' })
    expect(firstFieldErrors(undefined)).toEqual({})
  })
})
