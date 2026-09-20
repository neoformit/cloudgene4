<script setup>
import { ref, onMounted } from 'vue'
import { getGeneralSettings, updateGeneralSettings, getNavbar, updateNavbar } from '@/api/admin'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import { useServerStore } from '@/stores/server'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const server = useServerStore()
const settings = ref(null)
const navbar = ref([])
const loading = ref(true)
const saving = ref('')
const error = ref('')
const success = ref('')
const fields = ref({})
const navFields = ref({})

onMounted(async () => {
  try {
    const [g, n] = await Promise.all([getGeneralSettings(), getNavbar()])
    settings.value = g.data
    navbar.value = n.data.navbar
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load settings.')
  } finally {
    loading.value = false
  }
})

async function save() {
  error.value = ''
  success.value = ''
  fields.value = {}
  saving.value = 'general'
  try {
    const { data } = await updateGeneralSettings(settings.value)
    settings.value = data
    success.value = 'Settings saved.'
    server.load(true)
  } catch (err) {
    error.value = apiErrorMessage(err, 'Save failed.')
    fields.value = apiFieldErrors(err)
  } finally {
    saving.value = ''
  }
}

function addItem() {
  navbar.value.push({ title: '', url: '', icon: '', admin_only: false, auth_only: false })
}
function move(i, delta) {
  const j = i + delta
  if (j < 0 || j >= navbar.value.length) return
  const items = navbar.value
  ;[items[i], items[j]] = [items[j], items[i]]
}

async function saveNavbar() {
  error.value = ''
  success.value = ''
  navFields.value = {}
  saving.value = 'navbar'
  try {
    const { data } = await updateNavbar(navbar.value)
    navbar.value = data.navbar
    success.value = 'Navigation saved.'
    server.load(true)
  } catch (err) {
    error.value = apiErrorMessage(err, 'Save failed.')
    navFields.value = apiFieldErrors(err)
  } finally {
    saving.value = ''
  }
}

const navErr = (i, key) => navFields.value[`navbar[${i}].${key}`]?.[0]
</script>

<template>
  <AdminLayout>
    <h2 class="mb-4">General Settings</h2>

    <LoadingSpinner v-if="loading" />
    <AlertMessage :message="error" />
    <div v-if="success" class="alert alert-success" data-testid="settings-success">{{ success }}</div>

    <form v-if="settings" class="card mb-4" style="max-width: 48rem;" data-testid="general-form" @submit.prevent="save">
      <div class="card-header">Server</div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label" for="s-name">Service name</label>
          <input id="s-name" v-model="settings.name" class="form-control" :class="{ 'is-invalid': fields.name }" data-testid="settings-name" />
          <div class="invalid-feedback">{{ fields.name?.[0] }}</div>
        </div>
        <div class="mb-3">
          <label class="form-label" for="s-url">Public URL</label>
          <input id="s-url" v-model="settings.url" class="form-control" :class="{ 'is-invalid': fields.url }" placeholder="https://cloudgene.example.org" data-testid="settings-url" />
          <div class="invalid-feedback">{{ fields.url?.[0] }}</div>
          <div class="form-text">Used in e-mail links. Empty = the host of the request.</div>
        </div>
        <div class="row">
          <div class="col-sm-6 mb-3">
            <label class="form-label" for="s-maxrun">Max running jobs</label>
            <input id="s-maxrun" v-model.number="settings.max_running_jobs" type="number" min="1" class="form-control" :class="{ 'is-invalid': fields.max_running_jobs }" data-testid="settings-max-running" />
            <div class="invalid-feedback">{{ fields.max_running_jobs?.[0] }}</div>
          </div>
          <div class="col-sm-6 mb-3">
            <label class="form-label" for="s-maxqueue">Max queue size (waiting jobs)</label>
            <input id="s-maxqueue" v-model.number="settings.max_queue_size" type="number" min="0" class="form-control" :class="{ 'is-invalid': fields.max_queue_size }" data-testid="settings-max-queue" />
            <div class="invalid-feedback">{{ fields.max_queue_size?.[0] }}</div>
          </div>
          <div class="col-sm-6 mb-3">
            <label class="form-label" for="s-retention">Job retention (days, 0 = keep)</label>
            <input id="s-retention" v-model.number="settings.job_retention_days" type="number" min="0" class="form-control" :class="{ 'is-invalid': fields.job_retention_days }" data-testid="settings-retention" />
            <div class="invalid-feedback">{{ fields.job_retention_days?.[0] }}</div>
          </div>
          <div class="col-sm-6 mb-3">
            <label class="form-label" for="s-upload">Max upload per job (MB)</label>
            <input id="s-upload" v-model.number="settings.max_upload_mb" type="number" min="1" class="form-control" :class="{ 'is-invalid': fields.max_upload_mb }" data-testid="settings-max-upload" />
            <div class="invalid-feedback">{{ fields.max_upload_mb?.[0] }}</div>
          </div>
        </div>
        <div class="form-check form-switch mb-2">
          <input id="s-maint" v-model="settings.maintenance" type="checkbox" class="form-check-input" data-testid="settings-maintenance" />
          <label for="s-maint" class="form-check-label">Maintenance mode (blocks submissions by non-admins)</label>
        </div>
        <div class="mb-3">
          <label class="form-label" for="s-maintmsg">Maintenance message</label>
          <textarea id="s-maintmsg" v-model="settings.maintenance_message" rows="2" class="form-control" data-testid="settings-maintenance-message"></textarea>
        </div>
      </div>
      <div class="card-footer">
        <button class="btn btn-primary" type="submit" data-testid="settings-save" :disabled="!!saving">
          <span v-if="saving === 'general'" class="spinner-border spinner-border-sm me-1"></span>Save
        </button>
      </div>
    </form>

    <form v-if="settings" class="card" style="max-width: 64rem;" data-testid="navbar-form" @submit.prevent="saveNavbar">
      <div class="card-header">Navigation bar <small class="text-muted">(settings.yaml <code>navbar:</code>, in this order)</small></div>
      <div class="card-body p-0">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr><th>Title</th><th>URL</th><th>Icon</th><th>Logged-in only</th><th>Admins only</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, i) in navbar" :key="i" data-testid="navbar-row">
              <td>
                <input v-model="item.title" class="form-control form-control-sm" :class="{ 'is-invalid': navErr(i, 'title') }" data-testid="navbar-title" />
                <div class="invalid-feedback">{{ navErr(i, 'title') }}</div>
              </td>
              <td>
                <input v-model="item.url" class="form-control form-control-sm" :class="{ 'is-invalid': navErr(i, 'url') }" placeholder="/pages/about or https://…" data-testid="navbar-url" />
                <div class="invalid-feedback">{{ navErr(i, 'url') }}</div>
              </td>
              <td><input v-model="item.icon" class="form-control form-control-sm" placeholder="info-circle" style="width: 8rem;" data-testid="navbar-icon" /></td>
              <td class="text-center"><input v-model="item.auth_only" type="checkbox" class="form-check-input" data-testid="navbar-auth-only" /></td>
              <td class="text-center"><input v-model="item.admin_only" type="checkbox" class="form-check-input" data-testid="navbar-admin-only" /></td>
              <td class="text-nowrap text-end">
                <button type="button" class="btn btn-sm btn-link" title="Up" data-testid="navbar-up" @click="move(i, -1)"><i class="fas fa-arrow-up"></i></button>
                <button type="button" class="btn btn-sm btn-link" title="Down" data-testid="navbar-down" @click="move(i, 1)"><i class="fas fa-arrow-down"></i></button>
                <button type="button" class="btn btn-sm btn-link text-danger" title="Remove" data-testid="navbar-remove" @click="navbar.splice(i, 1)"><i class="fas fa-trash"></i></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-footer d-flex gap-2">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-testid="navbar-add" @click="addItem"><i class="fas fa-plus"></i> Add item</button>
        <button type="submit" class="btn btn-primary btn-sm" data-testid="navbar-save" :disabled="!!saving">
          <span v-if="saving === 'navbar'" class="spinner-border spinner-border-sm me-1"></span>Save navigation
        </button>
      </div>
    </form>
  </AdminLayout>
</template>
