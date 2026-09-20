<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getJob, getJobStatus, cancelJob, deleteJob, adminRestartJob, isActiveState } from '@/api/jobs'
import { apiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { usePolling } from '@/components/jobs/usePolling'
import JobStatusBadge from '@/components/jobs/JobStatusBadge.vue'
import JobProgress from '@/components/jobs/JobProgress.vue'
import JobLogTab from '@/components/jobs/JobLogTab.vue'
import JobResultsTab from '@/components/jobs/JobResultsTab.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const job = ref(null)
const loading = ref(true)
const error = ref('')
const actionError = ref('')
const activeTab = ref('details')
const confirmAction = ref(null)
const actionLoading = ref(false)
const now = ref(Date.now())
let clock = null

const active = computed(() => job.value && isActiveState(job.value.state))
const canRestart = computed(() => job.value?.can_restart && auth.isAdmin)

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}

function prettyDate(ts) {
  return ts ? new Date(ts).toLocaleString() : ''
}

const elapsed = computed(() => {
  const j = job.value
  if (!j?.started_at) return '-'
  const end = j.finished_at ? new Date(j.finished_at).getTime() : now.value
  const s = Math.max(0, Math.floor((end - new Date(j.started_at).getTime()) / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
})

async function loadJob() {
  const { data } = await getJob(route.params.id)
  job.value = data
}

/** Poll the light status endpoint; refetch the full job once it finishes. */
async function refreshStatus() {
  const before = job.value?.updated_at
  const { data } = await getJobStatus(route.params.id)
  const finishedNow = !isActiveState(data.state) && isActiveState(job.value?.state)
  job.value = { ...job.value, ...data }
  if (finishedNow) await loadJob()
  return data.updated_at !== before
}

const poller = usePolling(refreshStatus, {
  interval: 2000,
  maxInterval: 10000,
  shouldContinue: () => !!job.value && isActiveState(job.value.state),
})

onMounted(async () => {
  try {
    await loadJob()
    if (active.value) poller.start()
  } catch (e) {
    error.value = e.response?.status === 404
      ? 'Job not found or you do not have permission to view it.'
      : apiErrorMessage(e)
  } finally {
    loading.value = false
  }
  clock = setInterval(() => { now.value = Date.now() }, 1000)
})

onBeforeUnmount(() => clearInterval(clock))

async function performAction(action) {
  actionLoading.value = true
  actionError.value = ''
  try {
    if (action === 'cancel') {
      const { data } = await cancelJob(job.value.id)
      job.value = data
      if (active.value) poller.start()
    } else if (action === 'delete') {
      await deleteJob(job.value.id)
      router.push('/jobs')
      return
    } else if (action === 'restart') {
      const { data } = await adminRestartJob(job.value.id)
      job.value = data
      poller.start()
    }
  } catch (e) {
    actionError.value = apiErrorMessage(e)
  } finally {
    actionLoading.value = false
    confirmAction.value = null
  }
}
</script>

<template>
  <div>
    <LoadingSpinner v-if="loading" />

    <template v-else-if="job">
      <div class="page-header">
        <div class="py-1 container">
          <div class="d-flex justify-content-start align-items-center">
            <JobStatusBadge :state="job.state" with-label class="me-3 fs-6" />
            <div class="flex-grow-1">
              <h2 class="mb-0" data-testid="job-title">{{ job.name }}</h2>
              <small class="text-muted">
                <span title="Submitted"><i class="fas fa-clock"></i> {{ prettyDate(job.submitted_at) }}</span>&nbsp;&nbsp;
                <span title="Elapsed" data-testid="job-elapsed"><i class="fas fa-hourglass"></i> {{ elapsed }}</span>&nbsp;&nbsp;
                <span title="User" data-testid="job-user"><i class="fas fa-user"></i> {{ job.user?.username }}</span>&nbsp;&nbsp;
                <span title="Workflow" data-testid="job-workflow"><i class="fas fa-tag"></i> {{ job.workflow_name }} {{ job.workflow_version }}</span>
              </small>
            </div>
            <div class="ms-auto">
              <button v-if="canRestart" class="btn btn-light btn-sm me-1" title="Restart job"
                      data-testid="job-restart" @click="confirmAction = 'restart'">
                <i class="fas fa-undo"></i> Restart
              </button>
              <button v-if="job.can_cancel" class="btn btn-light btn-sm me-1" title="Cancel job"
                      data-testid="job-cancel" @click="confirmAction = 'cancel'">
                <i class="fas fa-times"></i> Cancel
              </button>
              <button v-if="job.can_delete" class="btn btn-light btn-sm" title="Delete job"
                      data-testid="job-delete" @click="confirmAction = 'delete'">
                <i class="fas fa-trash"></i> Delete
              </button>
            </div>
          </div>

          <div v-if="job.state === 'waiting'" data-testid="job-queue-position" class="alert alert-info mt-3 mb-0">
            <template v-if="job.cancel_requested">Cancelling…</template>
            <template v-else>
              Waiting in the queue<span v-if="job.queue_position"> at position <b>{{ job.queue_position }}</b></span>.
              The job starts as soon as a slot is free.
            </template>
          </div>
          <div v-if="job.state === 'running' && job.cancel_requested" class="alert alert-warning mt-3 mb-0"
               data-testid="job-cancelling">
            Cancelling… the pipeline is being stopped.
          </div>
          <AlertMessage :message="actionError" data-testid="job-action-error" class="mt-3 mb-0" />
        </div>
      </div>

      <div style="border-bottom: 1px solid #dee2e6; background: #fff;">
        <div class="container">
          <ul class="nav nav-tabs" style="border-bottom: 0;">
            <li class="nav-item">
              <button class="nav-link" :class="{ active: activeTab === 'details' }"
                      data-testid="job-tab-details" @click="activeTab = 'details'">Details</button>
            </li>
            <li class="nav-item">
              <button class="nav-link" :class="{ active: activeTab === 'results' }"
                      data-testid="job-tab-results" @click="activeTab = 'results'">
                Results <span v-if="job.outputs_count" class="badge bg-secondary">{{ job.outputs_count }}</span>
              </button>
            </li>
            <li class="nav-item">
              <button class="nav-link" :class="{ active: activeTab === 'logs' }"
                      data-testid="job-tab-logs" @click="activeTab = 'logs'">Logs</button>
            </li>
          </ul>
        </div>
      </div>

      <div class="py-4" style="background: #fff;">
        <div class="container">
          <template v-if="activeTab === 'details'">
            <div v-if="job.state === 'failed' && job.error_message" class="alert alert-danger"
                 style="white-space: pre-wrap" data-testid="job-failure">{{ job.error_message }}</div>
            <p v-if="job.state === 'waiting'" class="text-muted"><i>We will start your job as soon as possible.</i></p>
            <JobProgress :steps="job.steps || []" :messages="job.messages || []" />

            <h5 class="mt-4">Inputs</h5>
            <table class="table table-sm" data-testid="job-inputs">
              <tbody>
                <tr v-for="i in job.inputs || []" :key="i.id" :data-input-id="i.id">
                  <th class="w-25">{{ i.label }}</th>
                  <td style="white-space: pre-wrap">{{ typeof i.value === 'object' && i.value !== null ? JSON.stringify(i.value) : String(i.value) }}</td>
                </tr>
              </tbody>
            </table>
          </template>
          <JobResultsTab v-else-if="activeTab === 'results'" :job="job" />
          <JobLogTab v-else-if="activeTab === 'logs'" :job-id="job.id" :state="job.state" />
        </div>
      </div>
    </template>

    <div v-else class="container my-5">
      <AlertMessage :message="error" data-testid="job-error" />
    </div>

    <ConfirmDialog
      v-if="confirmAction === 'cancel'"
      title="Cancel Job"
      :message="`Are you sure you want to cancel <b>${escapeHtml(job?.name)}</b>?`"
      confirm-text="Cancel Job"
      confirm-class="btn-warning"
      :loading="actionLoading"
      data-testid="confirm-cancel"
      @confirm="performAction('cancel')"
      @cancel="confirmAction = null"
    />
    <ConfirmDialog
      v-if="confirmAction === 'delete'"
      title="Delete Job"
      :message="`Delete <b>${escapeHtml(job?.name)}</b> and all its results? This cannot be undone.`"
      confirm-text="Delete Job"
      confirm-class="btn-danger"
      :loading="actionLoading"
      data-testid="confirm-delete"
      @confirm="performAction('delete')"
      @cancel="confirmAction = null"
    />
    <ConfirmDialog
      v-if="confirmAction === 'restart'"
      title="Restart Job"
      :message="`Restart <b>${escapeHtml(job?.name)}</b> with the same inputs?`"
      confirm-text="Restart Job"
      confirm-class="btn-primary"
      :loading="actionLoading"
      data-testid="confirm-restart"
      @confirm="performAction('restart')"
      @cancel="confirmAction = null"
    />
  </div>
</template>
