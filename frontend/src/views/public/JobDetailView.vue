<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getJob, cancelJob, restartJob } from '@/api/jobs'
import { useAuthStore } from '@/stores/auth'
import JobStatusBadge from '@/components/jobs/JobStatusBadge.vue'
import JobStepsTab from '@/components/jobs/JobStepsTab.vue'
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
const activeTab = ref('steps')

const confirmAction = ref(null)
const actionLoading = ref(false)

let ws = null
let pollTimer = null

const activeStates = new Set(['pending', 'waiting', 'running'])
const canCancel = computed(() => job.value && activeStates.has(job.value.status))
const canRestart = computed(() => job.value?.status === 'failed' && auth.isAdmin)

function prettyDate(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString()
}

function prettyDuration(start, end) {
  if (!start) return '-'
  const endTime = end ? new Date(end) : new Date()
  const ms = endTime - new Date(start)
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

async function loadJob() {
  const { data } = await getJob(route.params.id)
  job.value = data
}

function connectWebSocket() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${route.params.id}/`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (job.value) {
      if (msg.status) job.value.status = msg.status
      if (msg.steps) job.value.steps = msg.steps
      if (msg.position !== undefined) job.value.queue_position = msg.position
    }
  }
  ws.onerror = () => startPolling()
  ws.onclose = () => {
    if (job.value && activeStates.has(job.value.status)) startPolling()
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    await loadJob()
    if (!activeStates.has(job.value?.status)) {
      clearInterval(pollTimer)
    }
  }, 20000)
}

onMounted(async () => {
  try {
    await loadJob()
    if (activeStates.has(job.value.status)) {
      try {
        connectWebSocket()
      } catch {
        startPolling()
      }
    }
  } catch {
    error.value = 'Job not found or you do not have permission to view it.'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  ws?.close()
  clearInterval(pollTimer)
})

async function performAction(action) {
  actionLoading.value = true
  try {
    if (action === 'cancel') {
      await cancelJob(job.value.id)
    } else if (action === 'restart') {
      await restartJob(job.value.id)
      router.push('/jobs')
      return
    }
    await loadJob()
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
            <JobStatusBadge :status="job.status" class="status me-3" />
            <div class="flex-grow-1">
              <h2 class="mb-0" data-testid="job-title">{{ job.name }}</h2>
              <small class="text-muted">
                <i class="fas fa-clock"></i> {{ prettyDate(job.submitted_at) }}&nbsp;&nbsp;
                <i class="fas fa-hourglass"></i> {{ prettyDuration(job.started_at, job.completed_at) }}&nbsp;&nbsp;
                <i class="fas fa-user"></i> {{ job.username }}&nbsp;&nbsp;
                <i class="fas fa-tag"></i> {{ job.workflow_id }}
              </small>
            </div>
            <div class="ms-auto">
              <button
                v-if="canRestart"
                class="btn btn-light btn-sm me-1"
                title="Restart job"
                @click="confirmAction = 'restart'"
              >
                <i class="fas fa-undo"></i>
              </button>
              <button
                v-if="canCancel"
                class="btn btn-light btn-sm"
                title="Cancel job"
                data-testid="job-cancel"
                @click="confirmAction = 'cancel'"
              >
                <i class="fas fa-times"></i>
              </button>
            </div>
          </div>

          <div v-if="job.status === 'waiting' || job.status === 'pending'" data-testid="job-queue-position" class="alert alert-info mt-3 mb-0">
            Job is in queue<span v-if="job.queue_position"> on position <b>{{ job.queue_position }}</b></span>.
          </div>
        </div>
      </div>

      <!-- Tab bar -->
      <div style="border-bottom: 1px solid #dee2e6; background: #fff;">
        <div class="container">
          <ul class="nav nav-tabs" style="border-bottom: 0;">
            <li class="nav-item">
              <button
                class="nav-link"
                :class="{ active: activeTab === 'steps' }"
                data-testid="job-tab-details"
                @click="activeTab = 'steps'"
              >Details</button>
            </li>
            <li class="nav-item">
              <button
                class="nav-link"
                :class="{ active: activeTab === 'results' }"
                data-testid="job-tab-results"
                @click="activeTab = 'results'"
              >Results</button>
            </li>
            <li class="nav-item">
              <button
                class="nav-link"
                :class="{ active: activeTab === 'logs' }"
                data-testid="job-tab-logs"
                @click="activeTab = 'logs'"
              >Logs</button>
            </li>
          </ul>
        </div>
      </div>

      <!-- Tab content -->
      <div class="py-4" style="background: #fff;">
        <div class="container">
          <div v-if="job.status === 'pending' || job.status === 'waiting'" class="text-muted">
            <i>This job is pending. We will start your job as soon as possible!</i>
          </div>

          <JobStepsTab v-if="activeTab === 'steps'" :job="job" />
          <JobResultsTab
            v-else-if="activeTab === 'results'"
            :job-id="job.id"
            :job-status="job.status"
          />
          <JobLogTab v-else-if="activeTab === 'logs'" :job-id="job.id" />
        </div>
      </div>
    </template>

    <div v-else class="container my-5">
      <AlertMessage :message="error" data-testid="job-error" />
    </div>

    <ConfirmDialog
      v-if="confirmAction === 'cancel'"
      title="Cancel Job"
      :message="`Are you sure you want to cancel <b>${job?.name}</b>?`"
      confirm-text="Cancel Job"
      confirm-class="btn-warning"
      :loading="actionLoading"
      @confirm="performAction('cancel')"
      @cancel="confirmAction = null"
    />
    <ConfirmDialog
      v-if="confirmAction === 'restart'"
      title="Restart Job"
      :message="`Are you sure you want to restart <b>${job?.name}</b>?`"
      confirm-text="Restart Job"
      confirm-class="btn-primary"
      :loading="actionLoading"
      @confirm="performAction('restart')"
      @cancel="confirmAction = null"
    />
  </div>
</template>
