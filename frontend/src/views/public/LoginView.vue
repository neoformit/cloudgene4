<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AlertMessage from '@/components/common/AlertMessage.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    const next = route.query.next || '/'
    router.push(next)
  } catch (e) {
    error.value = e.response?.data?.message || 'Invalid username or password.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="container page my-5 p-5">
    <h2>Sign in</h2>
    <br>

    <AlertMessage :message="error" data-testid="login-error" />

    <form class="form-horizontal" autocomplete="off" @submit.prevent="submit">
      <div class="mb-3">
        <label for="username" class="form-label">Username:</label>
        <input
          id="username"
          data-testid="login-username"
          v-model="username"
          type="text"
          class="form-control col-sm-3"
          autocomplete="off"
          required
        />
      </div>

      <div class="mb-3">
        <label for="password" class="form-label">Password:</label>
        <input
          id="password"
          data-testid="login-password"
          v-model="password"
          type="password"
          class="form-control col-sm-3"
          autocomplete="off"
          required
        />
      </div>

      <div class="mb-3">
        <button class="btn btn-primary" type="submit" data-testid="login-submit" :disabled="loading">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          Sign in
        </button>
      </div>
    </form>

    <hr>

    <p>New user? <RouterLink to="/register">Sign up for free</RouterLink></p>
    <p>Forgotten your password? <RouterLink to="/reset-password">Reset your password</RouterLink></p>
  </div>
</template>
