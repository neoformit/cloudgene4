<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import {
  getDashboard, pauseQueue, resumeQueue, enterMaintenance, exitMaintenance,
} from '@/api/admin'
import { apiErrorMessage } from '@/api/client'
import { useServerStore } from '@/stores/server'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const server = useServerStore()
const data = ref(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const maintenanceMessage = ref('')
let timer = null

const stateClass = {
  waiting: 'warning text-dark', running: 'primary', success: 'success', failed: 'danger',
  cancelled: 'secondary',
}

function prettyDate(ts) {
  return ts ? new Date(ts).toLocaleString() : '-'
}

async function load() {
  try {
    const res = await getDashboard()
    data.value = res.data
    if (!maintenanceMessage.value) maintenanceMessage.value = res.data.queue.maintenance_message
    error.value = ''
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load the dashboard.')
  } finally {
    loading.value = false
  }
}

async function act(fn) {
  busy.value = true
  error.value = ''
  try {
    const res = await fn()
    data.value = { ...data.value, queue: res.data }
    server.load(true) // maintenance banner
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 10000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <AdminLayout>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h2 class="mb-0">Dashboard</h2>
      <button class="btn btn-sm btn-outline-secondary" data-testid="dashboard-refresh" @click="load">
        <i class="fas fa-sync"></i> Refresh
      </button>
    </div>

    <AlertMessage :message="error" />
    <LoadingSpinner v-if="loading" />

    <template v-else-if="data">
      <!-- Queue -->
      <div class="card mb-4" data-testid="queue-card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span>Queue</span>
          <span>
            <span v-if="data.queue.worker.ok" class="badge bg-success" data-testid="worker-status" data-worker="ok">
              Worker alive (pid {{ data.queue.worker.pid }})
            </span>
            <span v-else class="badge bg-danger" data-testid="worker-status" data-worker="down">
              Worker not running{{ data.queue.worker.last_seen ? ` (last seen ${prettyDate(data.queue.worker.last_seen)})` : '' }}
            </span>
          </span>
        </div>
        <div class="card-body">
          <div class="row text-center mb-3">
            <div class="col">
              <div class="fs-3 fw-bold" data-testid="queue-running">{{ data.queue.running }}</div>
              <div class="small text-muted">running (max {{ data.queue.max_running }})</div>
            </div>
            <div class="col">
              <div class="fs-3 fw-bold" data-testid="queue-waiting">{{ data.queue.waiting }}</div>
              <div class="small text-muted">waiting (max {{ data.queue.max_queue }})</div>
            </div>
            <div class="col">
              <div class="fs-5 fw-bold" data-testid="queue-state" :data-paused="data.queue.paused">
                <span v-if="data.queue.paused" class="badge bg-warning text-dark">Paused</span>
                <span v-else class="badge bg-success">Active</span>
              </div>
              <div class="small text-muted">queue</div>
            </div>
            <div class="col">
              <div class="fs-5 fw-bold" data-testid="maintenance-state" :data-maintenance="data.queue.maintenance">
                <span v-if="data.queue.maintenance" class="badge bg-warning text-dark">On</span>
                <span v-else class="badge bg-secondary">Off</span>
              </div>
              <div class="small text-muted">maintenance</div>
            </div>
          </div>

          <div class="d-flex flex-wrap gap-2 align-items-start">
            <button
              v-if="data.queue.paused"
              class="btn btn-success btn-sm"
              data-testid="queue-resume"
              :disabled="busy"
              @click="act(resumeQueue)"
            >
              <i class="fas fa-play"></i> Resume queue
            </button>
            <button
              v-else
              class="btn btn-warning btn-sm"
              data-testid="queue-pause"
              :disabled="busy"
              @click="act(pauseQueue)"
            >
              <i class="fas fa-pause"></i> Pause queue
            </button>

            <template v-if="data.queue.maintenance">
              <button
                class="btn btn-outline-success btn-sm"
                data-testid="maintenance-exit"
                :disabled="busy"
                @click="act(exitMaintenance)"
              >
                <i class="fas fa-check"></i> Leave maintenance mode
              </button>
            </template>
            <div v-else class="input-group input-group-sm" style="max-width: 36rem;">
              <input
                v-model="maintenanceMessage"
                class="form-control"
                data-testid="maintenance-message"
                placeholder="Banner message"
              />
              <button
                class="btn btn-outline-warning"
                data-testid="maintenance-enter"
                :disabled="busy"
                @click="act(() => enterMaintenance(maintenanceMessage))"
              >
                <i class="fas fa-tools"></i> Enter maintenance mode
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Counts -->
      <div class="row g-3 mb-4">
        <div class="col-sm-6 col-lg-3">
          <div class="card"><div class="card-body">
            <div class="text-muted small">Jobs</div>
            <div class="fs-3 fw-bold" data-testid="count-jobs-total">{{ data.jobs.total }}</div>
            <div class="small">
              <span class="text-success" data-testid="count-jobs-success">{{ data.jobs.success }} ok</span> ·
              <span class="text-danger" data-testid="count-jobs-failed">{{ data.jobs.failed }} failed</span> ·
              <span class="text-muted" data-testid="count-jobs-cancelled">{{ data.jobs.cancelled }} cancelled</span>
            </div>
          </div></div>
        </div>
        <div class="col-sm-6 col-lg-3">
          <div class="card"><div class="card-body">
            <div class="text-muted small">Users</div>
            <div class="fs-3 fw-bold" data-testid="count-users-total">{{ data.users.total }}</div>
            <div class="small text-muted">{{ data.users.active }} active · {{ data.users.admins }} admins</div>
          </div></div>
        </div>
        <div class="col-sm-6 col-lg-3">
          <div class="card"><div class="card-body">
            <div class="text-muted small">Workflows</div>
            <div class="fs-3 fw-bold" data-testid="count-workflows-total">{{ data.workflows.total }}</div>
            <div class="small text-muted">
              <span data-testid="count-workflows-enabled">{{ data.workflows.enabled }}</span> enabled ·
              {{ data.workflows.disabled }} disabled ·
              <span :class="{ 'text-danger': data.workflows.invalid }">{{ data.workflows.invalid }} invalid</span>
            </div>
          </div></div>
        </div>
        <div class="col-sm-6 col-lg-3">
          <div class="card"><div class="card-body">
            <div class="text-muted small">Active jobs</div>
            <div class="fs-3 fw-bold" data-testid="count-jobs-active">{{ data.jobs.running + data.jobs.waiting }}</div>
            <div class="small text-muted">{{ data.jobs.running }} running · {{ data.jobs.waiting }} waiting</div>
          </div></div>
        </div>
      </div>

      <div class="card mb-4">
        <div class="card-header d-flex justify-content-between">
          <span>Recent jobs</span>
          <RouterLink to="/admin/jobs" class="small">All jobs &rarr;</RouterLink>
        </div>
        <div class="card-body p-0">
          <table class="table table-sm mb-0" data-testid="recent-jobs">
            <thead>
              <tr><th>Name</th><th>Workflow</th><th>User</th><th>Submitted</th><th>State</th></tr>
            </thead>
            <tbody>
              <tr v-for="job in data.recent_jobs" :key="job.id" data-testid="recent-job" :data-job-id="job.id">
                <td><RouterLink :to="`/jobs/${job.id}`">{{ job.name || job.id }}</RouterLink></td>
                <td><small>{{ job.workflow.name }}</small></td>
                <td><small>{{ job.user.username }}</small></td>
                <td><small>{{ prettyDate(job.submitted_at) }}</small></td>
                <td><span :class="`badge bg-${stateClass[job.state] || 'secondary'}`" :data-state="job.state">{{ job.state }}</span></td>
              </tr>
              <tr v-if="!data.recent_jobs.length">
                <td colspan="5" class="text-muted text-center">No jobs yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </AdminLayout>
</template>
