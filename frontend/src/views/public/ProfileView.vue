<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  createApiToken,
  deleteAccount,
  getProfile,
  revokeApiToken,
  updateProfile,
} from '@/api/users'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import {
  firstFieldErrors,
  normalizeEmail,
  validateEmail,
  validateFields,
  validateFullName,
  validatePassword,
} from '@/utils/validation'
import AlertMessage from '@/components/common/AlertMessage.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const auth = useAuthStore()
const router = useRouter()

const profile = ref(null)
const loadError = ref('')

// Personal information
const info = ref({ full_name: '', email: '', current_password: '' })
const infoErrors = ref({})
const infoError = ref('')
const infoSuccess = ref('')
const infoSaving = ref(false)
const emailChanged = computed(
  () => profile.value && normalizeEmail(info.value.email) !== profile.value.email
)

// Password
const pw = ref({ current_password: '', password: '', password_confirm: '' })
const pwErrors = ref({})
const pwError = ref('')
const pwSuccess = ref('')
const pwSaving = ref(false)

// API token
const tokenCreated = ref(null) // ISO date of the existing token, or null
const newToken = ref('') // shown once, right after creation
const tokenBusy = ref(false)
const tokenError = ref('')
const copied = ref(false)

// Delete account
const showDelete = ref(false)
const deletePassword = ref('')
const deleteError = ref('')
const deleting = ref(false)

function applyProfile(data) {
  profile.value = data
  info.value = { full_name: data.full_name, email: data.email, current_password: '' }
  tokenCreated.value = data.api_token?.created || null
  auth.updateUser(data)
}

onMounted(async () => {
  try {
    const { data } = await getProfile()
    applyProfile(data)
  } catch (e) {
    loadError.value = apiErrorMessage(e, 'Could not load your profile.')
  }
})

function showServerErrors(e, errorsRef, messageRef) {
  errorsRef.value = firstFieldErrors(apiFieldErrors(e))
  messageRef.value = Object.keys(errorsRef.value).length
    ? 'Please correct the marked fields.'
    : apiErrorMessage(e, 'Saving failed.')
}

async function saveInfo() {
  infoError.value = ''
  infoSuccess.value = ''
  const i = info.value
  infoErrors.value = validateFields({
    full_name: [validateFullName, i.full_name],
    email: [validateEmail, i.email],
  })
  if (emailChanged.value && !i.current_password) {
    infoErrors.value.current_password = 'Please enter your current password.'
  }
  if (Object.keys(infoErrors.value).length) return
  infoSaving.value = true
  try {
    const payload = { full_name: i.full_name, email: i.email }
    if (emailChanged.value) payload.current_password = i.current_password
    const { data } = await updateProfile(payload)
    applyProfile(data)
    infoSuccess.value = 'Your profile has been updated.'
  } catch (e) {
    showServerErrors(e, infoErrors, infoError)
  } finally {
    infoSaving.value = false
  }
}

async function savePassword() {
  pwError.value = ''
  pwSuccess.value = ''
  const p = pw.value
  pwErrors.value = validateFields({ password: [validatePassword, p.password, p.password_confirm] })
  if (!p.current_password) pwErrors.value.current_password = 'Please enter your current password.'
  if (Object.keys(pwErrors.value).length) return
  pwSaving.value = true
  try {
    const { data } = await updateProfile({ ...p })
    applyProfile(data)
    pw.value = { current_password: '', password: '', password_confirm: '' }
    pwSuccess.value = 'Your password has been changed.'
  } catch (e) {
    showServerErrors(e, pwErrors, pwError)
  } finally {
    pwSaving.value = false
  }
}

async function createToken() {
  tokenBusy.value = true
  tokenError.value = ''
  copied.value = false
  try {
    const { data } = await createApiToken()
    newToken.value = data.token
    tokenCreated.value = data.created
  } catch (e) {
    tokenError.value = apiErrorMessage(e, 'Could not create a token.')
  } finally {
    tokenBusy.value = false
  }
}

async function revokeToken() {
  tokenBusy.value = true
  tokenError.value = ''
  try {
    await revokeApiToken()
    newToken.value = ''
    tokenCreated.value = null
  } catch (e) {
    tokenError.value = apiErrorMessage(e, 'Could not revoke the token.')
  } finally {
    tokenBusy.value = false
  }
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(newToken.value)
    copied.value = true
  } catch {
    copied.value = false // clipboard unavailable (http, permissions): the token is selectable
  }
}

async function confirmDelete() {
  deleteError.value = ''
  if (!deletePassword.value) {
    deleteError.value = 'Please enter your password.'
    return
  }
  deleting.value = true
  try {
    await deleteAccount(deletePassword.value)
    auth._clear()
    router.push('/')
  } catch (e) {
    deleteError.value = firstFieldErrors(apiFieldErrors(e)).password || apiErrorMessage(e, 'Deleting failed.')
  } finally {
    deleting.value = false
  }
}

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : '')
</script>

<template>
  <div class="container page my-5 p-5">
    <h2>Account Settings</h2>
    <AlertMessage :message="loadError" data-testid="profile-load-error" />
    <LoadingSpinner v-if="!profile && !loadError" />

    <template v-if="profile">
      <p class="text-muted" data-testid="profile-username">
        Signed in as <strong>{{ profile.username }}</strong>
        <span v-if="profile.groups.length"> · groups: {{ profile.groups.join(', ') }}</span>
      </p>

      <!-- Personal information -->
      <form class="mb-5" novalidate data-testid="profile-form" @submit.prevent="saveInfo">
        <h4>Personal Information</h4>
        <AlertMessage :message="infoError" data-testid="profile-error" />
        <div v-if="infoSuccess" class="alert alert-success" data-testid="profile-success">{{ infoSuccess }}</div>

        <div class="mb-3">
          <label for="profile-full-name" class="form-label">Full Name:</label>
          <input
            id="profile-full-name"
            v-model="info.full_name"
            type="text"
            autocomplete="name"
            :class="['form-control', infoErrors.full_name ? 'is-invalid' : '']"
            data-testid="profile-full-name"
          />
          <div class="invalid-feedback">{{ infoErrors.full_name }}</div>
        </div>

        <div class="mb-3">
          <label for="profile-email" class="form-label">E-Mail:</label>
          <input
            id="profile-email"
            v-model="info.email"
            type="email"
            autocomplete="email"
            :class="['form-control', infoErrors.email ? 'is-invalid' : '']"
            data-testid="profile-email"
          />
          <div class="invalid-feedback" data-testid="profile-email-error">{{ infoErrors.email }}</div>
        </div>

        <div v-if="emailChanged" class="mb-3">
          <label for="profile-email-current-password" class="form-label">
            Current password (required to change your e-mail):
          </label>
          <input
            id="profile-email-current-password"
            v-model="info.current_password"
            type="password"
            autocomplete="current-password"
            :class="['form-control', infoErrors.current_password ? 'is-invalid' : '']"
            data-testid="profile-email-current-password"
          />
          <div class="invalid-feedback">{{ infoErrors.current_password }}</div>
        </div>

        <button class="btn btn-primary" type="submit" :disabled="infoSaving" data-testid="profile-save">
          <span v-if="infoSaving" class="spinner-border spinner-border-sm me-1"></span>
          Save
        </button>
      </form>

      <!-- Password -->
      <form class="mb-5" novalidate data-testid="password-form" @submit.prevent="savePassword">
        <h4>Change Password</h4>
        <AlertMessage :message="pwError" data-testid="password-error" />
        <div v-if="pwSuccess" class="alert alert-success" data-testid="password-success">{{ pwSuccess }}</div>

        <div class="mb-3">
          <label for="pw-current" class="form-label">Current Password:</label>
          <input
            id="pw-current"
            v-model="pw.current_password"
            type="password"
            autocomplete="current-password"
            :class="['form-control', pwErrors.current_password ? 'is-invalid' : '']"
            data-testid="password-current"
          />
          <div class="invalid-feedback" data-testid="password-current-error">{{ pwErrors.current_password }}</div>
        </div>
        <div class="mb-3">
          <label for="pw-new" class="form-label">New Password:</label>
          <input
            id="pw-new"
            v-model="pw.password"
            type="password"
            autocomplete="new-password"
            :class="['form-control', pwErrors.password ? 'is-invalid' : '']"
            data-testid="password-new"
          />
          <div class="invalid-feedback" data-testid="password-new-error">{{ pwErrors.password }}</div>
          <div v-if="!pwErrors.password" class="form-text">
            At least six characters with a digit, a lower- and an upper-case letter.
          </div>
        </div>
        <div class="mb-3">
          <label for="pw-confirm" class="form-label">New Password (again):</label>
          <input
            id="pw-confirm"
            v-model="pw.password_confirm"
            type="password"
            autocomplete="new-password"
            class="form-control"
            data-testid="password-confirm"
          />
        </div>
        <button class="btn btn-primary" type="submit" :disabled="pwSaving" data-testid="password-save">
          <span v-if="pwSaving" class="spinner-border spinner-border-sm me-1"></span>
          Change password
        </button>
      </form>

      <!-- API token -->
      <section class="mb-5" data-testid="token-section">
        <h4>API Access</h4>
        <p>
          The REST API lets you submit, monitor and download jobs from scripts. Send the token in
          the header <code>Authorization: Token &lt;your token&gt;</code>.
        </p>
        <AlertMessage :message="tokenError" data-testid="token-error" />

        <div v-if="newToken" class="alert alert-warning" data-testid="token-new">
          <div class="mb-2">Copy your new token now — it will not be shown again.</div>
          <div class="input-group">
            <input class="form-control font-monospace" :value="newToken" readonly data-testid="token-value" />
            <button class="btn btn-outline-secondary" type="button" data-testid="token-copy" @click="copyToken">
              <i class="fas fa-copy me-1"></i>{{ copied ? 'Copied' : 'Copy' }}
            </button>
          </div>
        </div>

        <p v-if="tokenCreated" data-testid="token-status" data-state="active">
          You have an API token (created {{ formatDate(tokenCreated) }}).
        </p>
        <p v-else class="text-muted" data-testid="token-status" data-state="none">You have no API token.</p>

        <button class="btn btn-primary me-2" :disabled="tokenBusy" data-testid="token-create" @click="createToken">
          <span v-if="tokenBusy" class="spinner-border spinner-border-sm me-1"></span>
          {{ tokenCreated ? 'Regenerate token' : 'Create API token' }}
        </button>
        <button
          v-if="tokenCreated"
          class="btn btn-outline-danger"
          :disabled="tokenBusy"
          data-testid="token-revoke"
          @click="revokeToken"
        >
          Revoke token
        </button>
      </section>

      <!-- Delete account -->
      <section data-testid="delete-section">
        <h4>Delete Account</h4>
        <p>Once you delete your account (and all your jobs), there is no going back.</p>
        <button
          v-if="!showDelete"
          class="btn btn-outline-danger"
          data-testid="delete-account"
          @click="showDelete = true"
        >
          Delete account…
        </button>
        <form v-else class="border border-danger rounded p-3" novalidate @submit.prevent="confirmDelete">
          <label for="delete-password" class="form-label">Enter your password to confirm:</label>
          <input
            id="delete-password"
            v-model="deletePassword"
            type="password"
            autocomplete="current-password"
            :class="['form-control mb-2', deleteError ? 'is-invalid' : '']"
            data-testid="delete-password"
          />
          <div class="invalid-feedback mb-2" data-testid="delete-error">{{ deleteError }}</div>
          <button class="btn btn-danger me-2" type="submit" :disabled="deleting" data-testid="delete-confirm">
            <span v-if="deleting" class="spinner-border spinner-border-sm me-1"></span>
            Permanently delete my account
          </button>
          <button class="btn btn-secondary" type="button" data-testid="delete-cancel" @click="showDelete = false">
            Cancel
          </button>
        </form>
      </section>
    </template>
  </div>
</template>
