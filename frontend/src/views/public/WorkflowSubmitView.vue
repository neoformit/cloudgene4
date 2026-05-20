<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getWorkflow } from '@/api/workflows'
import { submitJob } from '@/api/jobs'
import DynamicForm from '@/components/workflows/form/DynamicForm.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const route = useRoute()
const router = useRouter()

const workflow = ref(null)
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const jobName = ref('')

onMounted(async () => {
  try {
    const { data } = await getWorkflow(route.params.workflowId)
    workflow.value = data
    jobName.value = data.name
  } catch {
    error.value = 'Workflow not found.'
  } finally {
    loading.value = false
  }
})

const inputParams = () => workflow.value?.inputs ?? []

async function handleSubmit(formData) {
  error.value = ''
  submitting.value = true
  formData.append('workflow_id', route.params.workflowId)
  formData.set('job_name', jobName.value)
  try {
    const { data } = await submitJob(formData)
    router.push(`/jobs/${data.id}`)
  } catch (e) {
    const data = e.response?.data
    if (data?.error) {
      error.value = data.error
    } else if (data && typeof data === 'object') {
      const firstKey = Object.keys(data)[0]
      error.value = firstKey ? `${firstKey}: ${data[firstKey]}` : 'Job submission failed.'
    } else {
      error.value = 'Job submission failed.'
    }
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
          <h2>{{ workflow.name }}</h2>
          <small class="text-muted">{{ workflow.version }}</small>
          <p v-if="workflow.description" class="mt-1 mb-0">{{ workflow.description }}</p>
        </div>
      </div>

      <div class="container my-4">
        <ul class="nav nav-tabs mb-4">
          <li class="nav-item">
            <span class="nav-link active">Run</span>
          </li>
        </ul>

        <AlertMessage :message="error" />

        <form @submit.prevent="$refs.dynForm.onSubmit(jobName)">
          <div class="mb-4">
            <label for="job-name" class="form-label fw-semibold">Job Name:</label>
            <input
              id="job-name"
              v-model="jobName"
              type="text"
              class="form-control col-sm-3"
              required
            />
          </div>

          <DynamicForm
            ref="dynForm"
            :params="inputParams()"
            @submit="handleSubmit"
          />

          <div class="mt-4">
            <button class="btn btn-primary" type="submit" :disabled="submitting">
              <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
              {{ submitting ? 'Submitting…' : 'Submit Job' }}
            </button>
          </div>
        </form>
      </div>
    </template>

    <div v-else class="container my-5">
      <AlertMessage :message="error || 'Workflow not found.'" />
    </div>
  </div>
</template>
