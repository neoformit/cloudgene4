<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { confirmPasswordReset } from '@/api/auth'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import { firstFieldErrors, validatePassword } from '@/utils/validation'
import AlertMessage from '@/components/common/AlertMessage.vue'

const route = useRoute()

const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const fieldError = ref('')
const success = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  fieldError.value = validatePassword(password.value, confirmPassword.value) || ''
  if (fieldError.value) return
  loading.value = true
  try {
    const { data } = await confirmPasswordReset(route.params.token, password.value, confirmPassword.value)
    success.value = data.message
  } catch (e) {
    // invalid_token / expired_token → message; password rules → field error
    fieldError.value = firstFieldErrors(apiFieldErrors(e)).password || ''
    if (!fieldError.value) error.value = apiErrorMessage(e, 'Password reset failed.')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="container page my-5 p-5">
    <h2>Set New Password</h2>
    <br>

    <div v-if="success" class="alert alert-success" data-testid="recover-success">
      {{ success }} <RouterLink to="/login" data-testid="recover-login-link">Login now</RouterLink>.
    </div>

    <form v-else novalidate data-testid="recover-form" @submit.prevent="submit">
      <AlertMessage :message="error" data-testid="recover-error" />
      <p v-if="error"><RouterLink to="/reset-password">Request a new link</RouterLink></p>

      <div class="mb-3">
        <label for="new-password" class="form-label">New Password:</label>
        <input
          id="new-password"
          v-model="password"
          type="password"
          autocomplete="new-password"
          :class="['form-control', fieldError ? 'is-invalid' : '']"
          data-testid="recover-password"
        />
        <div class="invalid-feedback" data-testid="recover-password-error">{{ fieldError }}</div>
        <div v-if="!fieldError" class="form-text">
          At least six characters with a digit, a lower- and an upper-case letter.
        </div>
      </div>

      <div class="mb-3">
        <label for="confirm-password" class="form-label">Confirm Password:</label>
        <input
          id="confirm-password"
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          class="form-control"
          data-testid="recover-password-confirm"
        />
      </div>

      <button class="btn btn-primary" type="submit" :disabled="loading" data-testid="recover-submit">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
        Set password
      </button>
    </form>
  </div>
</template>
