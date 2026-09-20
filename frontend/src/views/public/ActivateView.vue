<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { activate } from '@/api/auth'
import { apiErrorMessage } from '@/api/client'

const route = useRoute()
// loading | activated | already_active | error
const status = ref('loading')
const message = ref('')

onMounted(async () => {
  try {
    const { data } = await activate(route.params.key)
    message.value = data.message
    status.value = data.status || 'activated'
  } catch (e) {
    message.value = apiErrorMessage(e, 'Activation failed. The link may be invalid.')
    status.value = 'error'
  }
})
</script>

<template>
  <div class="container page my-5 p-5">
    <h2>Account Activation</h2>
    <br>
    <div v-if="status === 'loading'" class="text-muted" data-testid="activate-loading">
      Activating your account…
    </div>
    <div
      v-else-if="status !== 'error'"
      class="alert alert-success"
      data-testid="activate-success"
      :data-status="status"
    >
      {{ message }} <RouterLink to="/login" data-testid="activate-login-link">Login now</RouterLink>.
    </div>
    <div v-else class="alert alert-danger" data-testid="activate-error">{{ message }}</div>
  </div>
</template>
