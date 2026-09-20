<script setup>
import { ref, onMounted } from 'vue'
import { getMailSettings, updateMailSettings, sendTestMail } from '@/api/admin'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const mail = ref(null)
const password = ref('') // write-only: never loaded from the server
const clearPassword = ref(false)
const testTo = ref('')
const loading = ref(true)
const saving = ref('')
const error = ref('')
const success = ref('')
const fields = ref({})

onMounted(async () => {
  try {
    mail.value = (await getMailSettings()).data
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load mail settings.')
  } finally {
    loading.value = false
  }
})

async function save() {
  error.value = ''
  success.value = ''
  fields.value = {}
  saving.value = 'save'
  try {
    const { password_set: _ignored, ...data } = mail.value
    if (password.value) data.password = password.value
    if (clearPassword.value) data.clear_password = true
    mail.value = (await updateMailSettings(data)).data
    password.value = ''
    clearPassword.value = false
    success.value = 'Mail settings saved.'
  } catch (err) {
    error.value = apiErrorMessage(err, 'Save failed.')
    fields.value = apiFieldErrors(err)
  } finally {
    saving.value = ''
  }
}

async function test() {
  error.value = ''
  success.value = ''
  fields.value = {}
  saving.value = 'test'
  try {
    const { data } = await sendTestMail(testTo.value)
    success.value = data.message
  } catch (err) {
    error.value = apiErrorMessage(err, 'Sending failed.')
    fields.value = apiFieldErrors(err)
  } finally {
    saving.value = ''
  }
}
</script>

<template>
  <AdminLayout>
    <h2 class="mb-4">Mail Settings</h2>
    <LoadingSpinner v-if="loading" />
    <AlertMessage :message="error" />
    <div v-if="success" class="alert alert-success" data-testid="mail-success">{{ success }}</div>

    <form v-if="mail" class="card mb-4" style="max-width: 48rem;" data-testid="mail-form" @submit.prevent="save">
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label" for="m-backend">Delivery</label>
          <select id="m-backend" v-model="mail.backend" class="form-select" data-testid="mail-backend">
            <option value="smtp">SMTP server</option>
            <option value="file">Write to files (development)</option>
            <option value="console">Print to server log (development)</option>
          </select>
        </div>
        <div v-if="mail.backend === 'file'" class="mb-3">
          <label class="form-label" for="m-path">Outbox directory</label>
          <input id="m-path" v-model="mail.file_path" class="form-control" data-testid="mail-file-path" />
          <div class="form-text">Relative to <code>$CLOUDGENE_HOME</code>.</div>
        </div>
        <template v-if="mail.backend === 'smtp'">
          <div class="row">
            <div class="col-sm-8 mb-3">
              <label class="form-label" for="m-host">SMTP host</label>
              <input id="m-host" v-model="mail.host" class="form-control" :class="{ 'is-invalid': fields.host }" data-testid="mail-host" />
              <div class="invalid-feedback">{{ fields.host?.[0] }}</div>
            </div>
            <div class="col-sm-4 mb-3">
              <label class="form-label" for="m-port">Port</label>
              <input id="m-port" v-model.number="mail.port" type="number" class="form-control" :class="{ 'is-invalid': fields.port }" data-testid="mail-port" />
              <div class="invalid-feedback">{{ fields.port?.[0] }}</div>
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label" for="m-user">Username</label>
              <input id="m-user" v-model="mail.user" class="form-control" autocomplete="off" data-testid="mail-user" />
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label" for="m-pass">Password</label>
              <input
                id="m-pass"
                v-model="password"
                type="password"
                class="form-control"
                autocomplete="new-password"
                :placeholder="mail.password_set ? '•••••• (unchanged)' : 'not set'"
                data-testid="mail-password"
              />
              <div v-if="mail.password_set" class="form-check mt-1">
                <input id="m-clear" v-model="clearPassword" type="checkbox" class="form-check-input" data-testid="mail-clear-password" />
                <label for="m-clear" class="form-check-label small">Remove stored password</label>
              </div>
            </div>
          </div>
          <div class="form-check form-check-inline mb-3">
            <input id="m-tls" v-model="mail.use_tls" type="checkbox" class="form-check-input" data-testid="mail-tls" />
            <label for="m-tls" class="form-check-label">STARTTLS</label>
          </div>
          <div class="form-check form-check-inline mb-3">
            <input id="m-ssl" v-model="mail.use_ssl" type="checkbox" class="form-check-input" :class="{ 'is-invalid': fields.use_ssl }" data-testid="mail-ssl" />
            <label for="m-ssl" class="form-check-label">SSL</label>
            <div class="invalid-feedback">{{ fields.use_ssl?.[0] }}</div>
          </div>
        </template>
        <div class="mb-3">
          <label class="form-label" for="m-from">Sender address</label>
          <input id="m-from" v-model="mail.from_email" type="email" class="form-control" :class="{ 'is-invalid': fields.from_email }" data-testid="mail-from" />
          <div class="invalid-feedback">{{ fields.from_email?.[0] }}</div>
        </div>
      </div>
      <div class="card-footer">
        <button class="btn btn-primary" type="submit" data-testid="mail-save" :disabled="!!saving">
          <span v-if="saving === 'save'" class="spinner-border spinner-border-sm me-1"></span>Save
        </button>
      </div>
    </form>

    <form v-if="mail" class="card" style="max-width: 48rem;" data-testid="mail-test-form" @submit.prevent="test">
      <div class="card-header">Send a test e-mail</div>
      <div class="card-body">
        <div class="input-group">
          <input v-model="testTo" type="email" class="form-control" :class="{ 'is-invalid': fields.to }" placeholder="Recipient (default: your own address)" data-testid="mail-test-to" />
          <button class="btn btn-outline-primary" type="submit" data-testid="mail-test-send" :disabled="!!saving">
            <span v-if="saving === 'test'" class="spinner-border spinner-border-sm me-1"></span>Send test e-mail
          </button>
        </div>
        <div class="form-text">Uses the saved settings — save first.</div>
      </div>
    </form>
  </AdminLayout>
</template>
