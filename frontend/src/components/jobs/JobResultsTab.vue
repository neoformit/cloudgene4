<script setup>
import { ref, onMounted } from 'vue'
import { listDownloads } from '@/api/jobs'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const props = defineProps({
  jobId: { type: String, required: true },
  jobStatus: { type: String, default: '' },
})

const downloads = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await listDownloads(props.jobId)
    downloads.value = data.results ?? data
  } finally {
    loading.value = false
  }
})

function downloadUrl(item) {
  return `/api/jobs/${props.jobId}/download/${item.id}/`
}
</script>

<template>
  <LoadingSpinner v-if="loading" />
  <div v-else>
    <div v-if="jobStatus === 'running'" class="alert alert-info">
      Job is still running. Results will appear here when the job completes.
    </div>
    <div v-else-if="!downloads.length" class="text-muted">
      <i>No result files available.</i>
    </div>
    <div v-else>
      <div v-for="item in downloads" :key="item.id" class="card mb-3 card-shadow">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <h6 class="card-title mb-1">{{ item.name || item.filename }}</h6>
              <small v-if="item.description" class="text-muted">{{ item.description }}</small>
            </div>
            <a
              :href="downloadUrl(item)"
              data-testid="job-output-link"
              :data-filename="item.filename || item.name"
              class="btn btn-sm btn-outline-primary ms-3"
              :download="item.filename"
            >
              <i class="fas fa-download me-1"></i>Download
            </a>
          </div>
          <div v-if="item.count !== undefined" class="mt-1">
            <small class="text-muted">Downloads: {{ item.count }}</small>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
