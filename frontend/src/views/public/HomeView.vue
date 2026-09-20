<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { listWorkflows } from '@/api/workflows'
import { getPage } from '@/api/server'
import { apiErrorMessage } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const auth = useAuthStore()

const homeHtml = ref('')
const workflows = ref([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  const [page, wfs] = await Promise.allSettled([getPage('home'), listWorkflows()])
  if (page.status === 'fulfilled') homeHtml.value = page.value.data.html
  if (wfs.status === 'fulfilled') {
    const data = wfs.value.data
    workflows.value = data.results ?? data
  } else {
    error.value = apiErrorMessage(wfs.reason, 'Could not load workflows.')
  }
  loading.value = false
})
</script>

<template>
  <div>
    <!-- home.html is admin-authored HTML from $CLOUDGENE_HOME/pages -->
    <div v-if="homeHtml" data-testid="home-content" class="fullsize-container" v-html="homeHtml"></div>

    <div class="container my-5">
      <LoadingSpinner v-if="loading" />
      <template v-else>
        <div v-if="error" class="alert alert-danger" data-testid="home-error">{{ error }}</div>
        <div v-if="workflows.length" class="row g-4" data-testid="workflow-list">
          <div
            v-for="wf in workflows"
            :key="wf.id"
            class="col-md-4"
            data-testid="workflow-card"
            :data-workflow-id="wf.id"
          >
            <div class="card h-100 card-shadow">
              <div class="card-body">
                <h5 class="card-title">{{ wf.name }}</h5>
                <!-- description may contain HTML (SPEC §4), authored by the admin -->
                <div class="card-text text-muted small" v-html="wf.description"></div>
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
                <RouterLink v-else to="/login" class="btn btn-outline-primary btn-sm" data-testid="workflow-login">
                  Login to run
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
        <p v-else-if="!error" class="text-muted" data-testid="no-workflows">
          No workflows are currently available{{ auth.isLoggedIn ? '' : ' — log in to see more' }}.
        </p>
      </template>
    </div>
  </div>
</template>
