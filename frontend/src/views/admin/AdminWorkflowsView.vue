<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  listAdminWorkflows, updateAdminWorkflow, reloadWorkflow, uninstallWorkflow,
  installWorkflow, syncWorkflows,
} from '@/api/admin'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const workflows = ref([])
const loading = ref(true)
const busy = ref('')
const error = ref('')
const success = ref('')
const confirmUninstall = ref(null)

const showInstall = ref(false)
const install = reactive({ path: '', public: false, groups: '', copy: false })
const installErrors = ref([])

async function load(fn = listAdminWorkflows) {
  try {
    workflows.value = (await fn()).data
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load workflows.')
  } finally {
    loading.value = false
  }
}

onMounted(() => load())

function flash(msg) {
  success.value = msg
  error.value = ''
}

async function run(key, fn, msg) {
  busy.value = key
  error.value = ''
  success.value = ''
  try {
    await fn()
    await load()
    if (msg) flash(msg)
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    busy.value = ''
  }
}

const toggleEnabled = (wf) =>
  run(`toggle-${wf.id}`, () => updateAdminWorkflow(wf.id, { enabled: !wf.enabled }),
    `${wf.name} ${wf.enabled ? 'disabled' : 'enabled'}.`)

async function reload(wf) {
  busy.value = `reload-${wf.id}`
  error.value = ''
  success.value = ''
  try {
    const { data } = await reloadWorkflow(wf.id)
    await load()
    if (data.valid) flash(`${data.name} reloaded.`)
    else error.value = `${wf.id}: ${data.errors.join('; ')}`
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    busy.value = ''
  }
}

const doSync = () => run('sync', () => load(syncWorkflows), 'All workflows re-read from settings.yaml.')

async function doUninstall() {
  const wf = confirmUninstall.value
  confirmUninstall.value = null
  await run(`uninstall-${wf.id}`, () => uninstallWorkflow(wf.id), `${wf.name} uninstalled.`)
}

async function doInstall() {
  busy.value = 'install'
  error.value = ''
  success.value = ''
  installErrors.value = []
  try {
    const groups = install.groups.split(',').map((g) => g.trim()).filter(Boolean)
    const { data } = await installWorkflow({
      path: install.path, public: install.public, groups, copy: install.copy,
    })
    Object.assign(install, { path: '', public: false, groups: '', copy: false })
    showInstall.value = false
    await load()
    flash(`${data.name} ${data.version} installed.`)
  } catch (err) {
    error.value = apiErrorMessage(err)
    installErrors.value = apiFieldErrors(err).path || []
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <AdminLayout>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h2 class="mb-0">Workflows</h2>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-outline-secondary" data-testid="workflows-sync" :disabled="!!busy" @click="doSync">
          <i class="fas fa-sync"></i> Reload all
        </button>
        <button class="btn btn-sm btn-primary" data-testid="workflow-install-open" @click="showInstall = !showInstall">
          <i class="fas fa-plus"></i> Install workflow
        </button>
      </div>
    </div>

    <form v-if="showInstall" class="card card-body mb-3" data-testid="workflow-install-form" @submit.prevent="doInstall">
      <div class="mb-2">
        <label class="form-label" for="install-path">Path</label>
        <input
          id="install-path"
          v-model.trim="install.path"
          class="form-control"
          :class="{ 'is-invalid': installErrors.length }"
          data-testid="workflow-install-path"
          placeholder="/srv/apps/my-app  or  my-app (relative to $CLOUDGENE_HOME/apps)"
          required
        />
        <div class="form-text">A directory containing <code>cloudgene.yaml</code>, or the YAML file itself.</div>
        <ul v-if="installErrors.length" class="invalid-feedback d-block mb-0" data-testid="workflow-install-errors">
          <li v-for="(e, i) in installErrors" :key="i">{{ e }}</li>
        </ul>
      </div>
      <div class="mb-2">
        <label class="form-label" for="install-groups">Groups</label>
        <input id="install-groups" v-model="install.groups" class="form-control" data-testid="workflow-install-groups" placeholder="comma-separated, e.g. researchers,admin" />
      </div>
      <div class="form-check">
        <input id="install-public" v-model="install.public" type="checkbox" class="form-check-input" data-testid="workflow-install-public" />
        <label class="form-check-label" for="install-public">Public (all users)</label>
      </div>
      <div class="form-check mb-2">
        <input id="install-copy" v-model="install.copy" type="checkbox" class="form-check-input" data-testid="workflow-install-copy" />
        <label class="form-check-label" for="install-copy">Copy into <code>$CLOUDGENE_HOME/apps/&lt;id&gt;</code></label>
      </div>
      <div>
        <button class="btn btn-primary btn-sm" type="submit" data-testid="workflow-install-submit" :disabled="busy === 'install'">
          <span v-if="busy === 'install'" class="spinner-border spinner-border-sm me-1"></span>Install
        </button>
      </div>
    </form>

    <AlertMessage :message="error" />
    <div v-if="success" class="alert alert-success" data-testid="workflows-success">{{ success }}</div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="card">
      <div class="card-body p-0">
        <table class="table table-sm table-hover align-middle mb-0" data-testid="admin-workflows-table">
          <thead>
            <tr><th>ID</th><th>Name</th><th>Version</th><th>Status</th><th>Access</th><th>Jobs</th><th></th></tr>
          </thead>
          <tbody>
            <tr
              v-for="wf in workflows"
              :key="wf.id"
              data-testid="admin-workflow-row"
              :data-workflow-id="wf.id"
              :data-enabled="wf.enabled"
              :data-valid="wf.valid"
            >
              <td><code>{{ wf.id }}</code></td>
              <td>{{ wf.name }}</td>
              <td><small>{{ wf.version }}</small></td>
              <td>
                <span v-if="!wf.valid" class="badge bg-danger" data-testid="workflow-status">invalid</span>
                <span v-else-if="wf.enabled" class="badge bg-success" data-testid="workflow-status">enabled</span>
                <span v-else class="badge bg-secondary" data-testid="workflow-status">disabled</span>
                <div v-if="!wf.valid" class="small text-danger mt-1" data-testid="workflow-errors">
                  <div v-for="(e, i) in wf.errors" :key="i">{{ e }}</div>
                </div>
              </td>
              <td data-testid="workflow-access">
                <span v-if="wf.public" class="badge bg-info">public</span>
                <span v-for="g in wf.groups" :key="g" class="badge bg-light text-dark border me-1">{{ g }}</span>
                <span v-if="!wf.public && !wf.groups.length" class="small text-muted">admins only</span>
              </td>
              <td><small>{{ wf.job_count }}</small></td>
              <td class="text-end text-nowrap">
                <button
                  class="btn btn-sm"
                  :class="wf.enabled ? 'btn-outline-secondary' : 'btn-outline-success'"
                  data-testid="workflow-toggle"
                  :disabled="!!busy"
                  @click="toggleEnabled(wf)"
                >
                  {{ wf.enabled ? 'Disable' : 'Enable' }}
                </button>
                <button class="btn btn-sm btn-outline-secondary ms-1" data-testid="workflow-reload" :disabled="!!busy" title="Re-read cloudgene.yaml" @click="reload(wf)">
                  <i class="fas fa-redo"></i>
                </button>
                <RouterLink :to="`/admin/workflows/${wf.id}`" class="btn btn-sm btn-outline-primary ms-1" data-testid="workflow-settings">
                  <i class="fas fa-cog"></i> Settings
                </RouterLink>
                <button class="btn btn-sm btn-outline-danger ms-1" data-testid="workflow-uninstall" :disabled="!!busy" @click="confirmUninstall = wf">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
            <tr v-if="!workflows.length">
              <td colspan="7" class="text-muted text-center">No workflows installed.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <ConfirmDialog
      v-if="confirmUninstall"
      title="Uninstall workflow"
      message="Remove this workflow from settings.yaml? Its files stay on disk and existing jobs are kept."
      confirm-text="Uninstall"
      @confirm="doUninstall"
      @cancel="confirmUninstall = null"
    />
  </AdminLayout>
</template>
