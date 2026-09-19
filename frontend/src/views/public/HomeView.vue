<script setup>
import { ref, onMounted, computed } from 'vue'
import { useServerStore } from '@/stores/server'
import { useAuthStore } from '@/stores/auth'
import { listWorkflows } from '@/api/workflows'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const server = useServerStore()
const auth = useAuthStore()

const workflows = ref([])
const loading = ref(true)

const homeHtml = computed(() => server.templates.home || '')

onMounted(async () => {
  try {
    const { data } = await listWorkflows()
    workflows.value = data.results ?? data
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <div v-if="homeHtml" data-testid="home-content" class="fullsize-container" v-html="homeHtml"></div>

    <div class="container my-5">
      <LoadingSpinner v-if="loading" />
      <template v-else>
        <div v-if="workflows.length" class="row g-4">
          <div v-for="wf in workflows" :key="wf.id" class="col-md-4" data-testid="workflow-card" :data-workflow-id="wf.id">
            <div class="card h-100 card-shadow">
              <div class="card-body">
                <h5 class="card-title">{{ wf.name }}</h5>
                <p class="card-text text-muted">{{ wf.description }}</p>
              </div>
              <div class="card-footer bg-transparent">
                <RouterLink
                  v-if="auth.isLoggedIn"
                  :to="`/run/${wf.id}`"
                  data-testid="workflow-run"
                  class="btn btn-primary btn-sm"
                >
                  Run
                </RouterLink>
                <RouterLink v-else to="/login" class="btn btn-outline-primary btn-sm">
                  Login to run
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
        <p v-else-if="!homeHtml" class="text-muted">No workflows are currently available.</p>
      </template>
    </div>
  </div>
</template>
