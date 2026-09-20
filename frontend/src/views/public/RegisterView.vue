<script setup>
import { ref } from 'vue'
import { register } from '@/api/auth'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import {
  validateEmail,
  validateFields,
  validateFullName,
  validatePassword,
  validateUsername,
  firstFieldErrors,
} from '@/utils/validation'
import AlertMessage from '@/components/common/AlertMessage.vue'

const form = ref({ username: '', full_name: '', email: '', password: '', password_confirm: '' })
const error = ref('')
const success = ref('')
const loading = ref(false)
const errors = ref({})

async function submit() {
  error.value = ''
  success.value = ''
  const f = form.value
  errors.value = validateFields({
    username: [validateUsername, f.username],
    full_name: [validateFullName, f.full_name],
    email: [validateEmail, f.email],
    password: [validatePassword, f.password, f.password_confirm],
  })
  if (Object.keys(errors.value).length) return

  loading.value = true
  try {
    const { data } = await register({ ...f })
    success.value = data.message
  } catch (e) {
    errors.value = firstFieldErrors(apiFieldErrors(e))
    error.value = Object.keys(errors.value).length
      ? 'Please correct the marked fields.'
      : apiErrorMessage(e, 'Registration failed. Please try again.')
  } finally {
    loading.value = false
  }
}

const fieldsSpec = [
  { key: 'username', label: 'Username', type: 'text', autocomplete: 'username',
    help: 'At least four characters: letters A–Z, a–z and digits only.' },
  { key: 'full_name', label: 'Full name', type: 'text', autocomplete: 'name' },
  { key: 'email', label: 'E-Mail', type: 'email', autocomplete: 'email' },
  { key: 'password', label: 'Password', type: 'password', autocomplete: 'new-password',
    help: 'At least six characters with a digit, a lower- and an upper-case letter.' },
  { key: 'password_confirm', label: 'Confirm password', type: 'password', autocomplete: 'new-password' },
]
</script>

<template>
  <div class="container page my-5 p-5">
    <h2>Sign up</h2>
    <br>

    <div v-if="success" class="alert alert-success" data-testid="register-success">
      {{ success }}
      <RouterLink to="/login">Go to login</RouterLink>
    </div>

    <form v-else id="signon-form" novalidate data-testid="register-form" @submit.prevent="submit">
      <AlertMessage :message="error" data-testid="register-error" />

      <div v-for="field in fieldsSpec" :key="field.key" class="mb-3">
        <label :for="`register-${field.key}`" class="form-label">{{ field.label }}:</label>
        <input
          :id="`register-${field.key}`"
          v-model="form[field.key]"
          :type="field.type"
          :autocomplete="field.autocomplete"
          :class="['form-control', errors[field.key] ? 'is-invalid' : '']"
          :data-testid="`register-${field.key.replace('_', '-')}`"
        />
        <div class="invalid-feedback" :data-testid="`register-${field.key.replace('_', '-')}-error`">
          {{ errors[field.key] }}
        </div>
        <div v-if="field.help && !errors[field.key]" class="form-text">{{ field.help }}</div>
      </div>

      <button class="btn btn-primary" type="submit" :disabled="loading" data-testid="register-submit">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
        Register
      </button>
    </form>
  </div>
</template>
