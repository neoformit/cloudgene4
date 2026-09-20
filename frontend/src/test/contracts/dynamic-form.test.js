/**
 * Run form: defaults, client validation (mirrors jobs/submission.py), multipart payload,
 * rendering of every SPEC §4 input type, and field-level errors.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DynamicForm from '@/components/workflows/form/DynamicForm.vue'
import {
  buildFormData, initialValues, validate, fileAccepted, formatBytes, editableParams,
} from '@/components/workflows/form/formModel'
import { createPoller } from '@/components/jobs/usePolling'
import { workflowFixture } from '../fixtures/jobs'

const params = workflowFixture.inputs
const csv = (name = 'data.csv', size = 10) => new File(['x'.repeat(size)], name, { type: 'text/csv' })

function validValues() {
  return { ...initialValues(params), data_file: [csv()], terms: true }
}

describe('initialValues', () => {
  it('uses YAML defaults for every type (F4)', () => {
    const v = initialValues(params)
    expect(v).toEqual({
      title: 'default text', count: '5', notes: 'first line', choice: 'b', mode: 'fast',
      flag: true, data_file: [], data_folder: [], hidden: 'secret', agb: false, terms: false,
    })
    expect('sep' in v).toBe(false)
  })

  it('editableParams skips display-only and hidden inputs', () => {
    expect(editableParams(params).map((p) => p.id)).not.toContain('hidden')
    expect(editableParams(params).map((p) => p.id)).not.toContain('info')
  })
})

describe('validate', () => {
  it('accepts valid values', () => {
    expect(validate(params, validValues())).toEqual({})
  })

  it('reports required, range, choice, terms and file errors like the server', () => {
    const errors = validate(params, {
      ...initialValues(params), title: '  ', count: '11', choice: 'zzz', data_file: [], terms: false,
    })
    expect(errors).toEqual({
      title: 'This field is required.',
      count: 'Must be at most 10.',
      choice: 'Select a valid choice.',
      data_file: 'Please select a file.',
      terms: 'You must accept this to submit the job.',
    })
    expect(validate(params, { ...validValues(), count: '0' }).count).toBe('Must be at least 1.')
    expect(validate(params, { ...validValues(), count: 'abc' }).count).toBe('Please enter a number.')
    expect(validate(params, { ...validValues(), count: '2.5e0' }).count).toBeUndefined()
  })

  it('checks accept, single file and total upload size', () => {
    expect(validate(params, { ...validValues(), data_file: [csv('x.exe')] }).data_file).toContain('not an accepted file type')
    expect(validate(params, { ...validValues(), data_file: [csv(), csv('b.csv')] }).data_file).toBe('Only one file can be uploaded here.')
    const big = { ...validValues(), data_folder: [csv('a.bin', 1024 * 1024 + 1)] }
    expect(validate(params, big, { maxUploadMb: 1 })._uploads).toContain('1 MB')
    expect(fileAccepted({ accept: '.vcf.gz, .csv' }, 'A.VCF.GZ')).toBe(true)
    expect(fileAccepted({ accept: 'text/plain' }, 'anything')).toBe(true)
  })

  it('optional agb checkbox may stay unchecked; job name length', () => {
    expect(validate(params, validValues()).agb).toBeUndefined()
    expect(validate(params, validValues(), { jobName: 'x'.repeat(256) }).job_name).toBeDefined()
    expect(validate(params, validValues(), { jobName: ' spaced   name 🚀 ' }).job_name).toBeUndefined()
  })
})

describe('buildFormData', () => {
  it('sends SPEC field names, typed text, explicit checkbox values and files', () => {
    const values = { ...validValues(), flag: false, data_folder: [csv('a b ü.csv'), csv('c.csv')] }
    const fd = buildFormData('all-inputs', '  My job name 🚀 ', params, values)
    expect(fd.get('workflow')).toBe('all-inputs')
    expect(fd.get('job_name')).toBe('  My job name 🚀 ')
    expect(fd.get('workflow_id')).toBeNull()
    expect(fd.get('title')).toBe('default text')
    expect(fd.get('count')).toBe('5')
    expect(fd.get('flag')).toBe('false')          // unchecked is still sent (F4)
    expect(fd.get('terms')).toBe('true')
    expect(fd.get('agb')).toBe('false')
    expect(fd.getAll('data_folder').map((f) => f.name)).toEqual(['a b ü.csv', 'c.csv'])
    expect(fd.get('data_file').name).toBe('data.csv')
    expect(fd.get('hidden')).toBeNull()           // server uses the YAML default
    expect(fd.get('sep')).toBeNull()
  })
})

describe('DynamicForm component', () => {
  function mountForm(extra = {}) {
    return mount(DynamicForm, {
      props: { params, modelValue: initialValues(params), ...extra },
    })
  }

  it('renders a wrapper per input with defaults and required markers (W2)', () => {
    const w = mountForm()
    for (const id of ['sep', 'info', 'title', 'count', 'notes', 'choice', 'mode', 'flag', 'data_file', 'data_folder', 'agb', 'terms']) {
      expect(w.find(`[data-testid="input-${id}"]`).exists(), id).toBe(true)
    }
    expect(w.find('[data-testid="input-hidden"]').exists()).toBe(false)
    expect(w.find('[data-testid="input-sep"]').element.tagName).toBe('HR')
    expect(w.find('[data-testid="input-info"]').html()).toContain('<b>info</b>')
    expect(w.find('[data-testid="input-title"] input').element.value).toBe('default text')
    const count = w.find('[data-testid="input-count"] input')
    expect(count.attributes('type')).toBe('number')
    expect(count.attributes('min')).toBe('1')
    expect(count.attributes('max')).toBe('10')
    expect(w.find('[data-testid="input-notes"] textarea').element.value).toBe('first line')
    expect(w.find('[data-testid="input-choice"] select').element.value).toBe('b')
    expect(w.find('[data-testid="input-mode"] input[value="fast"]').element.checked).toBe(true)
    expect(w.find('[data-testid="input-flag"] input').element.checked).toBe(true)
    expect(w.find('[data-testid="input-data_file"] input').attributes('accept')).toBe('.csv')
    expect(w.find('[data-testid="input-data_file"] input').attributes('multiple')).toBeUndefined()
    expect(w.find('[data-testid="input-data_folder"] input').attributes('multiple')).toBeDefined()
    expect(w.find('[data-testid="input-title"]').text()).toContain('*')
    expect(w.find('[data-testid="input-title"]').text()).toContain('Any text')
  })

  it('emits updated values', async () => {
    const w = mountForm()
    await w.find('[data-testid="input-title"] input').setValue('new')
    expect(w.emitted('update:modelValue').at(-1)[0].title).toBe('new')
    await w.find('[data-testid="input-flag"] input').setValue(false)
    expect(w.emitted('update:modelValue').at(-1)[0].flag).toBe(false)
    await w.find('[data-testid="input-mode"] input[value="accurate"]').setValue(true)
    expect(w.emitted('update:modelValue').at(-1)[0].mode).toBe('accurate')
  })

  it('shows field errors', () => {
    const w = mountForm({ errors: { count: 'Must be at most 10.' } })
    expect(w.find('[data-testid="error-count"]').text()).toBe('Must be at most 10.')
    expect(w.find('[data-testid="input-count"] input').classes()).toContain('is-invalid')
  })
})

describe('helpers', () => {
  it('formatBytes', () => {
    expect(formatBytes(500)).toBe('500 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
  })

  it('poller backs off without changes and stops when inactive', async () => {
    vi.useFakeTimers()
    let active = true
    const fn = vi.fn().mockResolvedValue(false)
    const p = createPoller(fn, { interval: 2000, maxInterval: 10000, shouldContinue: () => active })
    p.start()
    await vi.advanceTimersByTimeAsync(2000)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(p.delay).toBe(3000)
    await vi.advanceTimersByTimeAsync(3000)
    expect(p.delay).toBe(4500)
    fn.mockResolvedValue(true)
    await vi.advanceTimersByTimeAsync(4500)
    expect(p.delay).toBe(2000)
    active = false
    await vi.advanceTimersByTimeAsync(2000)
    expect(p.running).toBe(false)
    const calls = fn.mock.calls.length
    await vi.advanceTimersByTimeAsync(20000)
    expect(fn.mock.calls.length).toBe(calls)
    vi.useRealTimers()
  })
})
