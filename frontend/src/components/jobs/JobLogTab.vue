<script setup>
import { ref, onMounted, watch } from 'vue'
import { getJobLog, jobLogUrl } from '@/api/jobs'
import { apiErrorMessage } from '@/api/client'

const props = defineProps({
  jobId: { type: String, required: true },
  state: { type: String, default: '' },
})

const text = ref('')
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await getJobLog(props.jobId)
    text.value = data
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load the log.')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.state, load)
</script>

<template>
  <div data-testid="job-logs">
    <div class="d-flex justify-content-end mb-2 gap-2">
      <button class="btn btn-sm btn-outline-secondary" data-testid="job-log-refresh" @click="load">
        <i class="fas fa-sync"></i> Refresh
      </button>
      <a :href="jobLogUrl(jobId)" class="btn btn-sm btn-outline-secondary" target="_blank" data-testid="job-log-raw">
        <i class="fas fa-file-alt"></i> Raw log
      </a>
    </div>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <pre v-else class="bg-light p-3 border rounded small" style="max-height: 70vh; overflow: auto; white-space: pre-wrap"
         data-testid="job-log">{{ loading && !text ? 'Loading…' : text }}</pre>
  </div>
</template>
