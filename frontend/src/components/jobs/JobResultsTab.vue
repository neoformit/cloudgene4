<script setup>
import { computed } from 'vue'
import { formatBytes } from '@/components/workflows/form/formModel'

const props = defineProps({
  job: { type: Object, required: true },
})

const groups = computed(() => {
  const out = []
  const byId = {}
  for (const o of props.job.outputs || []) {
    if (!byId[o.output_id]) {
      byId[o.output_id] = { id: o.output_id, label: o.label || o.output_id, files: [] }
      out.push(byId[o.output_id])
    }
    byId[o.output_id].files.push(o)
  }
  return out
})

function displayPath(o) {
  // path is "<output id>/<rest>"; show the part inside the output folder
  const prefix = `${o.output_id}/`
  return o.path.startsWith(prefix) ? o.path.slice(prefix.length) : o.path
}
</script>

<template>
  <div data-testid="job-results">
    <p v-if="job.state === 'waiting' || job.state === 'running'" class="text-muted">
      Results will be available when the job has finished.
    </p>
    <p v-else-if="job.purged_at" class="text-muted" data-testid="job-results-expired">
      The results of this job have been deleted.
    </p>
    <p v-else-if="!groups.length" class="text-muted" data-testid="job-results-empty">No downloadable results.</p>

    <div v-for="g in groups" :key="g.id" class="mb-4" data-testid="job-output-group" :data-output-id="g.id">
      <h5>{{ g.label }}</h5>
      <ul class="list-group">
        <li v-for="o in g.files" :key="o.id" class="list-group-item d-flex justify-content-between align-items-center">
          <a :href="o.url" data-testid="job-output-link" :data-filename="o.path" download>
            <i class="fas fa-file-download me-2"></i>{{ displayPath(o) }}
          </a>
          <span class="text-muted small">
            {{ formatBytes(o.size) }}
            <span v-if="o.download_count" class="ms-2" title="Downloads"><i class="fas fa-download"></i> {{ o.download_count }}</span>
          </span>
        </li>
      </ul>
    </div>
    <p v-if="job.expires_at && groups.length" class="text-muted small" data-testid="job-expires">
      Results are kept until {{ new Date(job.expires_at).toLocaleString() }}.
    </p>
  </div>
</template>
