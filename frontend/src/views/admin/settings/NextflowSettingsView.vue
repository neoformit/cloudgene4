<script setup>
import { ref, onMounted } from 'vue'
import { getNextflowSettings, updateNextflowSettings } from '@/api/admin'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const nf = ref(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const fields = ref({})

onMounted(async () => {
  try {
    nf.value = (await getNextflowSettings()).data
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load Nextflow settings.')
  } finally {
    loading.value = false
  }
})

async function save() {
  error.value = ''
  success.value = ''
  fields.value = {}
  saving.value = true
  try {
    const { variables: _v, ...data } = nf.value
    nf.value = (await updateNextflowSettings(data)).data
    success.value = 'Nextflow settings saved.'
  } catch (err) {
    error.value = apiErrorMessage(err, 'Save failed.')
    fields.value = apiFieldErrors(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AdminLayout>
    <h2 class="mb-4">Nextflow Settings</h2>
    <LoadingSpinner v-if="loading" />
    <AlertMessage :message="error" />
    <div v-if="success" class="alert alert-success" data-testid="nextflow-success">{{ success }}</div>

    <form v-if="nf" class="card" style="max-width: 56rem;" data-testid="nextflow-form" @submit.prevent="save">
      <div class="card-body">
        <div class="row">
          <div class="col-md-4 mb-3">
            <label class="form-label" for="nf-binary">Nextflow executable</label>
            <input id="nf-binary" v-model="nf.binary" class="form-control" :class="{ 'is-invalid': fields.binary }" data-testid="nextflow-binary" />
            <div class="invalid-feedback">{{ fields.binary?.[0] }}</div>
          </div>
          <div class="col-md-4 mb-3">
            <label class="form-label" for="nf-profile">Default profile</label>
            <input id="nf-profile" v-model="nf.profile" class="form-control" placeholder="e.g. docker" data-testid="nextflow-profile" />
          </div>
          <div class="col-md-4 mb-3">
            <label class="form-label" for="nf-work">Work directory</label>
            <input id="nf-work" v-model="nf.work_dir" class="form-control" placeholder="empty = <job>/work" data-testid="nextflow-workdir" />
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label" for="nf-config">Global <code>nextflow.config</code></label>
          <textarea id="nf-config" v-model="nf.config" rows="10" class="form-control font-monospace" spellcheck="false" data-testid="nextflow-config"></textarea>
          <div class="form-text">Applied to every workflow; per-workflow files (Admin → Workflows → Settings) are applied after it.</div>
        </div>
        <div class="mb-3">
          <label class="form-label" for="nf-env">Global <code>nextflow.env</code></label>
          <textarea id="nf-env" v-model="nf.env" rows="4" class="form-control font-monospace" spellcheck="false" placeholder="KEY=value" data-testid="nextflow-env"></textarea>
        </div>
        <details>
          <summary class="small">Variables available in these files</summary>
          <table class="table table-sm small mt-2 mb-0" data-testid="nextflow-variables">
            <tbody>
              <tr v-for="v in nf.variables" :key="v.name">
                <td><code>{{ '${' + v.name + '}' }}</code></td><td>{{ v.description }}</td>
              </tr>
            </tbody>
          </table>
          <div class="form-text">Workflow- and job-specific variables are listed on each workflow's settings page.</div>
        </details>
      </div>
      <div class="card-footer">
        <button class="btn btn-primary" type="submit" data-testid="nextflow-save" :disabled="saving">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>Save
        </button>
      </div>
    </form>
  </AdminLayout>
</template>
