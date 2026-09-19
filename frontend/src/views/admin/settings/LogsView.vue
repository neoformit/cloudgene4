<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listLogs } from '@/api/admin'
import { apiErrorMessage } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import Pagination from '@/components/common/Pagination.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const LEVELS = ['debug', 'info', 'warning', 'error', 'critical']
const levelClass = {
  critical: 'text-danger fw-bold', error: 'text-danger', warning: 'text-warning',
  info: 'text-info', debug: 'text-secondary',
}

const logs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50
const loading = ref(true)
const error = ref('')
const filters = reactive({ min_level: '', component: '', search: '' })
const expanded = ref(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function fetchLogs(page = 1) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await listLogs({ ...filters, page, page_size: pageSize })
    logs.value = data.results
    total.value = data.count
    currentPage.value = page
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load logs.')
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchLogs())
</script>

<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <h2 class="mb-0">Logs</h2>
      <form class="d-flex gap-2" data-testid="logs-filters" @submit.prevent="fetchLogs(1)">
        <select v-model="filters.min_level" class="form-select form-select-sm" data-testid="logs-filter-level" @change="fetchLogs(1)">
          <option value="">All levels</option>
          <option v-for="l in LEVELS" :key="l" :value="l">{{ l }} and above</option>
        </select>
        <input v-model.trim="filters.component" class="form-control form-control-sm" placeholder="component (jobs, auth…)" data-testid="logs-filter-component" />
        <input v-model.trim="filters.search" class="form-control form-control-sm" placeholder="search message" data-testid="logs-filter-search" />
        <button class="btn btn-sm btn-outline-secondary" type="submit" data-testid="logs-filter-apply"><i class="fas fa-filter"></i></button>
      </form>
    </div>

    <AlertMessage :message="error" />
    <LoadingSpinner v-if="loading" />

    <template v-else>
      <div class="card mb-3">
        <div class="card-body p-0">
          <table class="table table-sm table-hover font-monospace mb-0" style="font-size: 0.8rem;" data-testid="logs-table">
            <thead>
              <tr><th>Time</th><th>Level</th><th>Component</th><th>User</th><th>Message</th></tr>
            </thead>
            <tbody>
              <template v-for="log in logs" :key="log.id">
                <tr data-testid="log-row" :data-level="log.level" :data-component="log.component" style="cursor: pointer;" @click="expanded = expanded === log.id ? null : log.id">
                  <td class="text-muted text-nowrap">{{ new Date(log.timestamp).toLocaleString() }}</td>
                  <td :class="levelClass[log.level] || ''">{{ log.level }}</td>
                  <td>{{ log.component }}</td>
                  <td>{{ log.username || '' }}</td>
                  <td data-testid="log-message">{{ log.message }}</td>
                </tr>
                <tr v-if="expanded === log.id && Object.keys(log.metadata || {}).length">
                  <td colspan="5"><pre class="mb-0 small">{{ JSON.stringify(log.metadata, null, 2) }}</pre></td>
                </tr>
              </template>
              <tr v-if="!logs.length">
                <td colspan="5" class="text-muted text-center">No log entries found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <Pagination :current-page="currentPage" :total-pages="totalPages" @change="fetchLogs" />
    </template>
  </AdminLayout>
</template>
