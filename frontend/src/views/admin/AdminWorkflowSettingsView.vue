<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  getAdminWorkflow, updateAdminWorkflow, reloadWorkflow, getWorkflowNextflow,
  updateWorkflowNextflow,
} from '@/api/admin'
import { listGroups } from '@/api/users'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'

const route = useRoute()
const id = route.params.id

const wf = ref(null)
const loading = ref(true)
const notFound = ref(false)
const error = ref('')
const success = ref('')
const saving = ref('')
const fieldErrors = ref({})

const allGroups = ref([])
const newGroup = ref('')
const access = reactive({ enabled: true, public: false, groups: [] })
const nf = reactive({ profile: '', work_dir: '', config: '', env: '' })
const nfMeta = reactive({ config_path: '', env_path: '', variables: [] })

const groupChoices = computed(() => {
  const names = new Set(allGroups.value.map((g) => g.name))
  access.groups.forEach((g) => names.add(g))
  return [...names].sort()
})

function applyWorkflow(data) {
  wf.value = data
  Object.assign(access, { enabled: data.enabled, public: data.public, groups: [...data.groups] })
}

function applyNextflow(data) {
  Object.assign(nf, { profile: data.profile, work_dir: data.work_dir, config: data.config, env: data.env })
  Object.assign(nfMeta, { config_path: data.config_path, env_path: data.env_path, variables: data.variables })
}

onMounted(async () => {
  try {
    const [w, n] = await Promise.all([getAdminWorkflow(id), getWorkflowNextflow(id)])
    applyWorkflow(w.data)
    applyNextflow(n.data)
  } catch (err) {
    if (err.response?.status === 404) notFound.value = true
    else error.value = apiErrorMessage(err, 'Could not load the workflow.')
  } finally {
    loading.value = false
  }
  try {
    const { data } = await listGroups()
    allGroups.value = data.results ?? data ?? []
  } catch {
    allGroups.value = []
  }
})

function addGroup() {
  const name = newGroup.value.trim()
  if (name && !access.groups.includes(name)) access.groups.push(name)
  newGroup.value = ''
}

async function save(kind, fn) {
  saving.value = kind
  error.value = ''
  success.value = ''
  fieldErrors.value = {}
  try {
    await fn()
    success.value = kind === 'access' ? 'Access settings saved.' : 'Nextflow settings saved.'
  } catch (err) {
    error.value = apiErrorMessage(err)
    fieldErrors.value = apiFieldErrors(err)
  } finally {
    saving.value = ''
  }
}

const saveAccess = () => save('access', async () => {
  const { data } = await updateAdminWorkflow(id, { ...access, groups: [...access.groups] })
  applyWorkflow(data)
})

const saveNextflow = () => save('nextflow', async () => {
  const { data } = await updateWorkflowNextflow(id, { ...nf })
  applyNextflow(data)
})

async function reload() {
  saving.value = 'reload'
  error.value = ''
  success.value = ''
  try {
    const { data } = await reloadWorkflow(id)
    applyWorkflow(data)
    if (data.valid) success.value = 'cloudgene.yaml re-read.'
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    saving.value = ''
  }
}
</script>

<template>
  <AdminLayout>
    <RouterLink to="/admin/workflows" class="small">&larr; Workflows</RouterLink>
    <LoadingSpinner v-if="loading" />

    <div v-else-if="notFound" class="alert alert-warning mt-3" data-testid="workflow-not-found">Workflow not found.</div>

    <template v-else-if="wf">
      <div class="d-flex justify-content-between align-items-start mt-2 mb-3">
        <div>
          <h2 class="mb-1" data-testid="workflow-admin-title">{{ wf.name }}</h2>
          <p class="text-muted mb-0"><code>{{ wf.id }}</code> &middot; v{{ wf.version }} &middot; <small>{{ wf.yaml_path }}</small></p>
        </div>
        <button class="btn btn-sm btn-outline-secondary" data-testid="workflow-reload" :disabled="!!saving" @click="reload">
          <i class="fas fa-redo"></i> Reload YAML
        </button>
      </div>

      <AlertMessage :message="error" />
      <div v-if="success" class="alert alert-success" data-testid="workflow-settings-success">{{ success }}</div>
      <div v-if="!wf.valid" class="alert alert-danger" data-testid="workflow-errors">
        <strong>This workflow is invalid and cannot be run:</strong>
        <ul class="mb-0"><li v-for="(e, i) in wf.errors" :key="i">{{ e }}</li></ul>
      </div>
      <div v-if="wf.warnings?.length" class="alert alert-warning">
        <ul class="mb-0"><li v-for="(w, i) in wf.warnings" :key="i">{{ w }}</li></ul>
      </div>

      <!-- Access -->
      <form class="card mb-4" data-testid="workflow-access-form" @submit.prevent="saveAccess">
        <div class="card-header">Access</div>
        <div class="card-body">
          <div class="form-check form-switch">
            <input id="wf-enabled" v-model="access.enabled" type="checkbox" class="form-check-input" data-testid="workflow-enabled" />
            <label class="form-check-label" for="wf-enabled">Enabled</label>
          </div>
          <div class="form-check form-switch mb-3">
            <input id="wf-public" v-model="access.public" type="checkbox" class="form-check-input" data-testid="workflow-public" />
            <label class="form-check-label" for="wf-public">Public — every user (and anonymous visitors in the list) can see it</label>
          </div>
          <div class="mb-1 fw-semibold small">Groups allowed to run it <span class="text-muted fw-normal">(admins always can)</span></div>
          <div v-for="g in groupChoices" :key="g" class="form-check form-check-inline">
            <input :id="`wf-g-${g}`" v-model="access.groups" :value="g" type="checkbox" class="form-check-input" :data-testid="`workflow-group-${g}`" />
            <label :for="`wf-g-${g}`" class="form-check-label">{{ g }}</label>
          </div>
          <div class="input-group input-group-sm mt-2" style="max-width: 20rem;">
            <input v-model="newGroup" class="form-control" placeholder="Add group by name" data-testid="workflow-group-new" @keydown.enter.prevent="addGroup" />
            <button class="btn btn-outline-secondary" type="button" data-testid="workflow-group-add" @click="addGroup">Add</button>
          </div>
        </div>
        <div class="card-footer">
          <button class="btn btn-primary btn-sm" type="submit" data-testid="workflow-access-save" :disabled="!!saving">
            <span v-if="saving === 'access'" class="spinner-border spinner-border-sm me-1"></span>Save access
          </button>
        </div>
      </form>

      <!-- Nextflow -->
      <form class="card mb-4" data-testid="workflow-nextflow-form" @submit.prevent="saveNextflow">
        <div class="card-header">Nextflow (this workflow)</div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-6 mb-3">
              <label class="form-label" for="wf-profile">Profile</label>
              <input id="wf-profile" v-model="nf.profile" class="form-control" :class="{ 'is-invalid': fieldErrors.profile }" placeholder="empty = global default" data-testid="workflow-nf-profile" />
              <div class="invalid-feedback">{{ fieldErrors.profile?.[0] }}</div>
            </div>
            <div class="col-md-6 mb-3">
              <label class="form-label" for="wf-workdir">Work directory</label>
              <input id="wf-workdir" v-model="nf.work_dir" class="form-control" placeholder="empty = global default" data-testid="workflow-nf-workdir" />
            </div>
          </div>
          <div class="mb-3">
            <label class="form-label" for="wf-config">nextflow.config <small class="text-muted">{{ nfMeta.config_path }}</small></label>
            <textarea id="wf-config" v-model="nf.config" class="form-control font-monospace" rows="8" spellcheck="false" data-testid="workflow-nf-config"></textarea>
            <div class="form-text">Applied after the global config for jobs of this workflow.</div>
          </div>
          <div class="mb-3">
            <label class="form-label" for="wf-env">nextflow.env <small class="text-muted">{{ nfMeta.env_path }}</small></label>
            <textarea id="wf-env" v-model="nf.env" class="form-control font-monospace" rows="4" spellcheck="false" placeholder="KEY=value" data-testid="workflow-nf-env"></textarea>
          </div>
          <details>
            <summary class="small">Variables available in these files</summary>
            <table class="table table-sm small mt-2 mb-0" data-testid="workflow-nf-variables">
              <tbody>
                <tr v-for="v in nfMeta.variables" :key="v.name">
                  <td><code>{{ '${' + v.name + '}' }}</code></td><td>{{ v.scope }}</td><td>{{ v.description }}</td>
                </tr>
              </tbody>
            </table>
          </details>
        </div>
        <div class="card-footer">
          <button class="btn btn-primary btn-sm" type="submit" data-testid="workflow-nf-save" :disabled="!!saving">
            <span v-if="saving === 'nextflow'" class="spinner-border spinner-border-sm me-1"></span>Save Nextflow settings
          </button>
        </div>
      </form>

      <div class="card">
        <div class="card-header">cloudgene.yaml</div>
        <pre class="card-body mb-0 small bg-light" data-testid="workflow-yaml">{{ wf.yaml }}</pre>
      </div>
    </template>

    <AlertMessage v-else :message="error" />
  </AdminLayout>
</template>
