/**
 * Contract tests for DynamicForm component
 * 
 * These tests validate that the DynamicForm component correctly creates FormData
 * objects that match the backend API contract expectations, preventing the
 * "formData.append is not a function" error that occurred previously.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DynamicForm from '@/components/workflows/form/DynamicForm.vue'

// Mock all the form input components
vi.mock('@/components/workflows/form/TextInput.vue', () => ({
  default: {
    template: '<input type="text" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['param', 'modelValue'],
    emits: ['update:modelValue']
  }
}))

vi.mock('@/components/workflows/form/FileInput.vue', () => ({
  default: {
    template: '<input type="file" @change="handleFileChange" />',
    props: ['param', 'modelValue', 'multiple'],
    emits: ['update:modelValue'],
    methods: {
      handleFileChange(event) {
        const file = event.target.files[0]
        this.$emit('update:modelValue', file)
      }
    }
  }
}))

vi.mock('@/components/workflows/form/CheckboxInput.vue', () => ({
  default: {
    template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
    props: ['param', 'modelValue'],
    emits: ['update:modelValue']
  }
}))

// Mock other input components as simple divs since they're not used in these tests
// vi.mock factories are hoisted above imports, so shared values must be hoisted too
const { mockComponent } = vi.hoisted(() => ({
  mockComponent: { template: '<div></div>', props: ['param', 'modelValue'], emits: ['update:modelValue'] },
}))
vi.mock('@/components/workflows/form/TextareaInput.vue', () => ({ default: mockComponent }))
vi.mock('@/components/workflows/form/SelectInput.vue', () => ({ default: mockComponent }))
vi.mock('@/components/workflows/form/RadioInput.vue', () => ({ default: mockComponent }))
vi.mock('@/components/workflows/form/TermsInput.vue', () => ({ default: mockComponent }))

describe('DynamicForm Component Contract', () => {
  let wrapper

  beforeEach(() => {
    // Clear any previous mocks
    vi.clearAllMocks()
  })

  describe('FormData Creation Contract', () => {
    it('should create valid FormData object for text parameters', () => {
      const params = [
        {
          id: 'text_param',
          type: 'text',
          value: '',
          required: true
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'test-job-name' }
      })

      // Simulate user input
      const textInput = wrapper.find('input[type="text"]')
      textInput.setValue('test value')

      // Get reference to the onSubmit method
      const form = wrapper.vm

      // Call onSubmit
      form.onSubmit()

      // Verify emit was called with FormData
      expect(wrapper.emitted('submit')).toHaveLength(1)

      // Extract and validate the FormData
      const formData = wrapper.emitted('submit')[0][0]
      expect(formData).toBeInstanceOf(FormData)
      expect(formData.get('job_name')).toBe('test-job-name')
      expect(formData.get('text_param')).toBe('test value')
    })

    it('should create valid FormData object for file parameters', () => {
      const params = [
        {
          id: 'file_param',
          type: 'file',
          required: true
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'file-job-name' }
      })

      // Create a mock file
      const mockFile = new File(['test content'], 'test.txt', { type: 'text/plain' })

      // Simulate file selection by directly updating the component's values
      wrapper.vm.values.file_param = mockFile

      // Call onSubmit
      wrapper.vm.onSubmit()

      expect(wrapper.emitted('submit')).toHaveLength(1)

      const formData = wrapper.emitted('submit')[0][0]
      expect(formData).toBeInstanceOf(FormData)
      expect(formData.get('job_name')).toBe('file-job-name')
      expect(formData.get('file_param').name).toBe(mockFile.name)
    })

    it('should create valid FormData object for mixed parameter types', () => {
      const params = [
        {
          id: 'text_param',
          type: 'text',
          value: 'default text'
        },
        {
          id: 'file_param',
          type: 'file'
        },
        {
          id: 'checkbox_param',
          type: 'checkbox'
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'mixed-job' }
      })

      // Set up test values
      const mockFile = new File(['content'], 'data.txt')
      wrapper.vm.values.text_param = 'updated text'
      wrapper.vm.values.file_param = mockFile
      wrapper.vm.values.checkbox_param = true

      wrapper.vm.onSubmit()

      expect(wrapper.emitted('submit')).toHaveLength(1)

      const formData = wrapper.emitted('submit')[0][0]
      expect(formData.get('job_name')).toBe('mixed-job')
      expect(formData.get('text_param')).toBe('updated text')
      expect(formData.get('file_param').name).toBe(mockFile.name)
      expect(formData.get('checkbox_param')).toBe('true') // FormData converts to string
    })

    it('should handle array values correctly', () => {
      const params = [
        {
          id: 'multi_file_param',
          type: 'folder' // This type allows multiple files
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'array-job' }
      })

      // Set up array of files
      const files = [
        new File(['content1'], 'file1.txt'),
        new File(['content2'], 'file2.txt')
      ]
      wrapper.vm.values.multi_file_param = files

      wrapper.vm.onSubmit()

      expect(wrapper.emitted('submit')).toHaveLength(1)

      const formData = wrapper.emitted('submit')[0][0]
      
      // FormData.getAll() should return all values for the same key
      const allFiles = formData.getAll('multi_file_param')
      expect(allFiles).toHaveLength(2)
      expect(allFiles[0].name).toBe(files[0].name)
      expect(allFiles[1].name).toBe(files[1].name)
    })

    it('should exclude empty and null values from FormData', () => {
      const params = [
        {
          id: 'empty_text',
          type: 'text',
          value: ''
        },
        {
          id: 'null_text',
          type: 'text',
          value: null
        },
        {
          id: 'undefined_text',
          type: 'text'
        },
        {
          id: 'valid_text',
          type: 'text',
          value: 'valid value'
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'exclusion-test' }
      })

      // Explicitly set some values to empty/null/undefined
      wrapper.vm.values.empty_text = ''
      wrapper.vm.values.null_text = null
      wrapper.vm.values.undefined_text = undefined
      wrapper.vm.values.valid_text = 'valid value'

      wrapper.vm.onSubmit()

      const formData = wrapper.emitted('submit')[0][0]
      
      // Only job_name and valid_text should be in FormData
      expect(formData.get('job_name')).toBe('exclusion-test')
      expect(formData.get('valid_text')).toBe('valid value')
      expect(formData.get('empty_text')).toBeNull()
      expect(formData.get('null_text')).toBeNull()
      expect(formData.get('undefined_text')).toBeNull()
    })

    it('should properly handle checkbox boolean values', () => {
      const params = [
        {
          id: 'checkbox_true',
          type: 'checkbox'
        },
        {
          id: 'checkbox_false', 
          type: 'checkbox'
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'checkbox-test' }
      })

      wrapper.vm.values.checkbox_true = true
      wrapper.vm.values.checkbox_false = false

      wrapper.vm.onSubmit()

      const formData = wrapper.emitted('submit')[0][0]
      
      // Both states are sent so the server never sees a "missing" checkbox (F4)
      expect(formData.get('checkbox_true')).toBe('true')
      expect(formData.get('checkbox_false')).toBe('false')
    })
  })

  describe('Component Initialization Contract', () => {
    it('should initialize values correctly for different parameter types', () => {
      const params = [
        {
          id: 'text_with_default',
          type: 'text',
          value: 'default value'
        },
        {
          id: 'text_without_default',
          type: 'text'
        },
        {
          id: 'checkbox_param',
          type: 'checkbox'
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: '' }
      })

      // Verify initial values
      expect(wrapper.vm.values.text_with_default).toBe('default value')
      expect(wrapper.vm.values.text_without_default).toBe('')
      expect(wrapper.vm.values.checkbox_param).toBe(false)
    })
  })

  describe('Parameter Type Handling Contract', () => {
    it('should recognize all supported parameter types', () => {
      const params = [
        { id: 'text', type: 'text' },
        { id: 'number', type: 'number' },
        { id: 'string', type: 'string' },
        { id: 'textarea', type: 'textarea' },
        { id: 'list', type: 'list' },
        { id: 'radio', type: 'radio' },
        { id: 'checkbox', type: 'checkbox' },
        { id: 'file', type: 'file' },
        { id: 'local_file', type: 'local_file' },
        { id: 'hdfs_file', type: 'hdfs_file' },
        { id: 'folder', type: 'folder' },
        { id: 'local_folder', type: 'local_folder' },
        { id: 'hdfs_folder', type: 'hdfs_folder' }
      ]

      // This should not throw any errors
      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: '' }
      })

      // Verify all parameters are initialized
      params.forEach(param => {
        expect(wrapper.vm.values).toHaveProperty(param.id)
      })
    })
  })

  describe('Error Prevention Contract', () => {
    it('should always emit FormData object, never plain object', () => {
      const params = [
        {
          id: 'test_param',
          type: 'text',
          value: 'test'
        }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: 'error-prevention-test' }
      })

      wrapper.vm.onSubmit()

      // Verify the emitted value has FormData methods
      const emittedData = wrapper.emitted('submit')[0][0]
      expect(emittedData).toBeInstanceOf(FormData)
      expect(typeof emittedData.append).toBe('function')
      expect(typeof emittedData.get).toBe('function')
      expect(typeof emittedData.set).toBe('function')
    })

    it('sends an empty job name (server generates the default name, K3)', () => {
      const params = [
        { id: 'param1', type: 'text', value: 'value1' }
      ]

      wrapper = mount(DynamicForm, {
        props: { params, workflowId: 'wf', jobName: '' }
      })

      // Call without name parameter
      wrapper.vm.onSubmit()

      const formData = wrapper.emitted('submit')[0][0]
      expect(formData).toBeInstanceOf(FormData)
      expect(formData.get('job_name')).toBe('')
      expect(formData.get('workflow_id')).toBe('wf')
    })
  })
})