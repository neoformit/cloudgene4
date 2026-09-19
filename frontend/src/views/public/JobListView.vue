<script setup>
import { ref, computed, onMounted } from 'vue'
import { listJobs, cancelJob, deleteJob, isActiveState, JOB_STATES } from '@/api/jobs'
import { apiErrorMessage } from '@/api/client'
import { usePolling } from '@/components/jobs/usePolling'
import JobStatusBadge from '@/components/jobs/JobStatusBadge.vue'
import Pagination from '@/components/common/Pagination.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const jobs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const stateFilter = ref('')
const loading = ref(true)
const error = ref('')

const confirm = ref(null) // {action: 'cancel'|'delete', job}
const confirmLoading = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const hasActive = computed(() => jobs.value.some((j) => isActiveState(j.state)))

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}

function prettyDate(ts) {
  return ts ? new Date(ts).toLocaleString() : ''
}

function prettyDuration(seconds) {
  if (seconds === null || seconds === undefined) return '-'
  const s = Math.floor(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

async function fetchJobs(page = currentPage.value) {
  const params = { page, page_size: pageSize }
  if (stateFilter.value) params.state = stateFilter.value
  const before = JSON.stringify(jobs.value.map((j) => [j.id, j.state, j.queue_position]))
  const { data } = await listJobs(params)
  jobs.value = data.results ?? data
  total.value = data.count ?? jobs.value.length
  currentPage.value = page
  if (hasActive.value) poller.start()
  return JSON.stringify(jobs.value.map((j) => [j.id, j.state, j.queue_position])) !== before
}

const poller = usePolling(() => fetchJobs(), {
  interval: 3000,
  maxInterval: 10000,
  shouldContinue: () => hasActive.value,
})

async function reload(page = 1) {
  error.value = ''
  try {
    await fetchJobs(page)
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load jobs.')
  } finally {
    loading.value = false
  }
}

onMounted(() => reload(1))

async function performAction() {
  const { action, job } = confirm.value
  confirmLoading.value = true
  try {
    if (action === 'cancel') await cancelJob(job.id)
    else await deleteJob(job.id)
    await fetchJobs(currentPage.value)
  } catch (e) {
    error.value = apiErrorMessage(e)
  } finally {
    confirmLoading.value = false
    confirm.value = null
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <div class="py-1 container d-flex align-items-center">
        <h2 class="mb-0 me-auto">Jobs</h2>
        <label class="me-2 text-muted small" for="job-state-filter">State</label>
        <select id="job-state-filter" v-model="stateFilter" class="form-select form-select-sm w-auto"
                data-testid="job-filter-state" @change="reload(1)">
          <option value="">All</option>
          <option value="waiting,running">Active</option>
          <option v-for="s in JOB_STATES" :key="s" :value="s">{{ s.charAt(0).toUpperCase() + s.slice(1) }}</option>
        </select>
      </div>
    </div>

    <div class="container my-4">
      <AlertMessage :message="error" data-testid="jobs-error" />
      <LoadingSpinner v-if="loading" />

      <template v-else>
        <div v-if="!jobs.length" class="text-center text-muted py-5" data-testid="jobs-empty">
          <i class="fas fa-inbox fa-3x mb-3 d-block"></i>
          <p v-if="stateFilter">No jobs in this state.</p>
          <p v-else>No jobs yet. <router-link to="/">Run a workflow</router-link> to get started.</p>
        </div>

        <table v-else class="table table-hover align-middle" data-testid="jobs-table">
          <thead>
            <tr>
              <th style="width: 3rem"></th>
              <th>Name</th>
              <th>Workflow</th>
              <th>Submitted</th>
              <th>Duration</th>
              <th class="text-end">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in jobs" :key="job.id" data-testid="job-row" :data-job-id="job.id" :data-state="job.state">
              <td><JobStatusBadge :state="job.state" testid="job-row-state" /></td>
              <td>
                <router-link :to="`/jobs/${job.id}`" data-testid="job-row-link">{{ job.name }}</router-link>
                <div v-if="job.state === 'waiting' && job.queue_position" class="small text-muted" data-testid="job-row-queue">
                  Queue position {{ job.queue_position }}
                </div>
                <div v-if="job.cancel_requested && job.state === 'running'" class="small text-warning">Cancelling…</div>
              </td>
              <td>{{ job.workflow_name }} <small class="text-muted">{{ job.workflow_version }}</small></td>
              <td>{{ prettyDate(job.submitted_at) }}</td>
              <td>{{ prettyDuration(job.duration_seconds) }}</td>
              <td class="text-end">
                <button v-if="job.can_cancel" class="btn btn-sm btn-outline-warning me-1" title="Cancel"
                        data-testid="job-row-cancel" @click="confirm = { action: 'cancel', job }">
                  <i class="fas fa-times"></i>
                </button>
                <button v-if="job.can_delete" class="btn btn-sm btn-outline-danger" title="Delete"
                        data-testid="job-row-delete" @click="confirm = { action: 'delete', job }">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <Pagination :current-page="currentPage" :total-pages="totalPages" @change="reload" />
      </template>
    </div>

    <ConfirmDialog
      v-if="confirm"
      :title="confirm.action === 'cancel' ? 'Cancel Job' : 'Delete Job'"
      :message="confirm.action === 'cancel'
        ? `Are you sure you want to cancel <b>${escapeHtml(confirm.job.name)}</b>?`
        : `Delete <b>${escapeHtml(confirm.job.name)}</b> and all its results? This cannot be undone.`"
      :confirm-text="confirm.action === 'cancel' ? 'Cancel Job' : 'Delete Job'"
      :confirm-class="confirm.action === 'cancel' ? 'btn-warning' : 'btn-danger'"
      :loading="confirmLoading"
      @confirm="performAction"
      @cancel="confirm = null"
    />
  </div>
</template>
