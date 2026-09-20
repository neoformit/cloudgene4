<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listAdminJobs, cancelAdminJob, restartAdminJob, listAdminWorkflows } from '@/api/admin'
import { apiErrorMessage } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import Pagination from '@/components/common/Pagination.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

// Contract: GET /api/admin/jobs?state=&user=&workflow=&page= (SPEC §3.6, implemented by T03)
// → {count, results: [{id, name, state, workflow: {id, name}, user: {username}, submitted_at,
//    started_at, finished_at}]}; POST /api/admin/jobs/{id}/cancel|restart.
const STATES = ['waiting', 'running', 'success', 'failed', 'cancelled']
const ACTIVE = ['waiting', 'running']
const RESTARTABLE = ['failed', 'cancelled']
const stateClass = {
  waiting: 'warning text-dark', running: 'primary', success: 'success', failed: 'danger',
  cancelled: 'secondary',
}

const jobs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const loading = ref(true)
const error = ref('')
const success = ref('')
const workflows = ref([])
const filters = reactive({ state: '', user: '', workflow: '' })
const confirm = ref(null) // {job, action}
const confirmLoading = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const stateOf = (job) => job.state ?? job.status
const workflowName = (job) => job.workflow?.name ?? job.workflow_name ?? ''
const username = (job) => job.user?.username ?? job.user_username ?? ''
const prettyDate = (ts) => (ts ? new Date(ts).toLocaleString() : '-')

async function fetchJobs(page = 1) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await listAdminJobs({ ...filters, page })
    jobs.value = data.results ?? data
    total.value = data.count ?? jobs.value.length
    currentPage.value = page
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load jobs.')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  fetchJobs()
  try {
    workflows.value = (await listAdminWorkflows()).data
  } catch {
    workflows.value = []
  }
})

function resetFilters() {
  Object.assign(filters, { state: '', user: '', workflow: '' })
  fetchJobs(1)
}

async function doConfirm() {
  const { job, action } = confirm.value
  confirmLoading.value = true
  error.value = ''
  success.value = ''
  try {
    if (action === 'cancel') await cancelAdminJob(job.id)
    else await restartAdminJob(job.id)
    success.value = `Job "${job.name || job.id}" ${action === 'cancel' ? 'cancelled' : 'restarted'}.`
    await fetchJobs(currentPage.value)
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    confirmLoading.value = false
    confirm.value = null
  }
}
</script>

<template>
  <AdminLayout>
    <h2 class="mb-3">Jobs</h2>

    <form class="row g-2 align-items-end mb-3" data-testid="jobs-filters" @submit.prevent="fetchJobs(1)">
      <div class="col-auto">
        <label class="form-label small mb-0" for="f-state">State</label>
        <select id="f-state" v-model="filters.state" class="form-select form-select-sm" data-testid="jobs-filter-state" @change="fetchJobs(1)">
          <option value="">All states</option>
          <option v-for="s in STATES" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <div class="col-auto">
        <label class="form-label small mb-0" for="f-wf">Workflow</label>
        <select id="f-wf" v-model="filters.workflow" class="form-select form-select-sm" data-testid="jobs-filter-workflow" @change="fetchJobs(1)">
          <option value="">All workflows</option>
          <option v-for="wf in workflows" :key="wf.id" :value="wf.id">{{ wf.name }}</option>
        </select>
      </div>
      <div class="col-auto">
        <label class="form-label small mb-0" for="f-user">User</label>
        <input id="f-user" v-model.trim="filters.user" class="form-control form-control-sm" placeholder="username" data-testid="jobs-filter-user" />
      </div>
      <div class="col-auto">
        <button class="btn btn-sm btn-primary" type="submit" data-testid="jobs-filter-apply"><i class="fas fa-filter"></i> Filter</button>
        <button class="btn btn-sm btn-link" type="button" data-testid="jobs-filter-reset" @click="resetFilters">Reset</button>
      </div>
    </form>

    <AlertMessage :message="error" />
    <div v-if="success" class="alert alert-success" data-testid="jobs-success">{{ success }}</div>

    <LoadingSpinner v-if="loading" />

    <template v-else>
      <div class="card mb-3">
        <div class="card-body p-0">
          <table class="table table-sm table-hover mb-0" data-testid="admin-jobs-table">
            <thead>
              <tr>
                <th>State</th><th>Name</th><th>Workflow</th><th>User</th>
                <th>Submitted</th><th>Finished</th><th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="job in jobs" :key="job.id" data-testid="admin-job-row" :data-job-id="job.id" :data-state="stateOf(job)">
                <td><span :class="`badge bg-${stateClass[stateOf(job)] || 'secondary'}`">{{ stateOf(job) }}</span></td>
                <td><RouterLink :to="`/jobs/${job.id}`">{{ job.name || job.id }}</RouterLink></td>
                <td><small>{{ workflowName(job) }}</small></td>
                <td><small>{{ username(job) }}</small></td>
                <td><small>{{ prettyDate(job.submitted_at) }}</small></td>
                <td><small>{{ prettyDate(job.finished_at ?? job.completed_at) }}</small></td>
                <td class="text-end text-nowrap">
                  <button
                    v-if="ACTIVE.includes(stateOf(job))"
                    class="btn btn-sm btn-outline-warning"
                    data-testid="admin-job-cancel"
                    @click="confirm = { job, action: 'cancel' }"
                  >
                    <i class="fas fa-times"></i> Cancel
                  </button>
                  <button
                    v-if="RESTARTABLE.includes(stateOf(job))"
                    class="btn btn-sm btn-outline-primary"
                    data-testid="admin-job-restart"
                    @click="confirm = { job, action: 'restart' }"
                  >
                    <i class="fas fa-redo"></i> Restart
                  </button>
                </td>
              </tr>
              <tr v-if="!jobs.length">
                <td colspan="7" class="text-muted text-center" data-testid="admin-jobs-empty">No jobs found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <Pagination :current-page="currentPage" :total-pages="totalPages" @change="fetchJobs" />
    </template>

    <ConfirmDialog
      v-if="confirm"
      :title="confirm.action === 'cancel' ? 'Cancel job' : 'Restart job'"
      :message="`${confirm.action === 'cancel' ? 'Cancel' : 'Restart'} this job?`"
      :confirm-text="confirm.action === 'cancel' ? 'Cancel job' : 'Restart job'"
      :confirm-class="confirm.action === 'cancel' ? 'btn-warning' : 'btn-primary'"
      :loading="confirmLoading"
      @confirm="doConfirm"
      @cancel="confirm = null"
    />
  </AdminLayout>
</template>
