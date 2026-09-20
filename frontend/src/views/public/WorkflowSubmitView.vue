<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getWorkflow } from '@/api/workflows'
import { submitJob } from '@/api/jobs'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import DynamicForm from '@/components/workflows/form/DynamicForm.vue'
import { buildFormData, initialValues, validate, MAX_JOB_NAME } from '@/components/workflows/form/formModel'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const route = useRoute()
const router = useRouter()

const workflow = ref(null)
const loading = ref(true)
const loadError = ref('')
const submitting = ref(false)
const error = ref('')
const errors = ref({})
const jobName = ref('')
const values = ref({})

const params = computed(() => workflow.value?.inputs ?? [])

onMounted(async () => {
  try {
    const { data } = await getWorkflow(route.params.workflowId)
    workflow.value = data
    values.value = initialValues(data.inputs)
  } catch (e) {
    loadError.value = e.response?.status === 404 ? 'Workflow not found.' : apiErrorMessage(e)
  } finally {
    loading.value = false
  }
})

async function handleSubmit() {
  error.value = ''
  errors.value = validate(params.value, values.value, {
    maxUploadMb: workflow.value?.max_upload_mb,
    jobName: jobName.value,
  })
  if (Object.keys(errors.value).length) {
    error.value = errors.value._uploads || 'Please correct the highlighted fields.'
    return
  }
  submitting.value = true
  try {
    const fd = buildFormData(workflow.value.id, jobName.value, params.value, values.value)
    const { data } = await submitJob(fd)
    router.push(`/jobs/${data.id}`)
  } catch (e) {
    const fields = apiFieldErrors(e)
    errors.value = Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.join(' ')]))
    error.value = apiErrorMessage(e, 'Job submission failed.')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <LoadingSpinner v-if="loading" />

    <template v-else-if="workflow">
      <div class="page-header">
        <div class="py-1 container">
          <h2 data-testid="workflow-title">{{ workflow.name }}</h2>
          <small class="text-muted" data-testid="workflow-version">{{ workflow.version }}</small>
          <p v-if="workflow.description" class="mt-1 mb-0" v-html="workflow.description"></p>
        </div>
      </div>

      <div class="container my-4">
        <ul class="nav nav-tabs mb-4">
          <li class="nav-item">
            <span class="nav-link active">Run</span>
          </li>
        </ul>

        <AlertMessage v-if="workflow.definition_errors?.length" data-testid="workflow-definition-error"
          :message="`This workflow is misconfigured: ${workflow.definition_errors.join('; ')}`" />

        <form data-testid="run-form" novalidate @submit.prevent="handleSubmit">
          <div class="mb-4">
            <label for="job-name" class="form-label fw-semibold">Job name <span class="text-muted fw-normal">(optional)</span></label>
            <input
              id="job-name"
              data-testid="job-name"
              v-model="jobName"
              type="text"
              class="form-control"
              :class="{ 'is-invalid': errors.job_name }"
              :maxlength="MAX_JOB_NAME"
              :placeholder="`${workflow.name} <date>`"
            />
            <div v-if="errors.job_name" class="invalid-feedback d-block" data-testid="error-job_name">{{ errors.job_name }}</div>
          </div>

          <DynamicForm v-model="values" :params="params" :errors="errors" :disabled="submitting" />

          <AlertMessage :message="error" data-testid="run-error" />

          <div class="mt-4">
            <button class="btn btn-primary" type="submit" data-testid="job-submit" :disabled="submitting">
              <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
              {{ submitting ? 'Submitting…' : 'Submit Job' }}
            </button>
          </div>
        </form>
      </div>
    </template>

    <div v-else class="container my-5">
      <AlertMessage :message="loadError || 'Workflow not found.'" data-testid="run-error" />
    </div>
  </div>
</template>
