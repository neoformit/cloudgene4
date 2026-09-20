<script setup>
import { ref } from 'vue'
import { requestPasswordReset } from '@/api/auth'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import { firstFieldErrors } from '@/utils/validation'
import AlertMessage from '@/components/common/AlertMessage.vue'

const email = ref('')
const error = ref('')
const fieldError = ref('')
const success = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  fieldError.value = ''
  success.value = ''
  if (!email.value.trim()) {
    fieldError.value = 'E-Mail is required.'
    return
  }
  loading.value = true
  try {
    // The server answers the same for every address (it never reveals whether it exists).
    const { data } = await requestPasswordReset(email.value.trim())
    success.value = data.message
  } catch (e) {
    fieldError.value = firstFieldErrors(apiFieldErrors(e)).email || ''
    if (!fieldError.value) error.value = apiErrorMessage(e, 'Request failed. Please try again.')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="container page my-5 p-5">
    <h2>Reset Password</h2>
    <p>Enter the e-mail address of your account. We will send you a link to choose a new password.</p>

    <div v-if="success" class="alert alert-success" data-testid="reset-success">{{ success }}</div>

    <form v-else novalidate data-testid="reset-form" @submit.prevent="submit">
      <AlertMessage :message="error" data-testid="reset-error" />

      <div class="mb-3">
        <label for="email" class="form-label">E-Mail:</label>
        <input
          id="email"
          v-model="email"
          type="email"
          autocomplete="email"
          :class="['form-control', fieldError ? 'is-invalid' : '']"
          data-testid="reset-email"
        />
        <div class="invalid-feedback" data-testid="reset-email-error">{{ fieldError }}</div>
      </div>

      <button class="btn btn-primary" type="submit" :disabled="loading" data-testid="reset-submit">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
        Send reset link
      </button>
    </form>

    <hr class="mt-4">
    <p><RouterLink to="/login">Back to login</RouterLink></p>
  </div>
</template>
