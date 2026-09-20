<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getPage } from '@/api/server'
import { apiErrorMessage } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const route = useRoute()
const html = ref('')
const loading = ref(true)
const notFound = ref(false)
const error = ref('')

async function load(slug) {
  loading.value = true
  notFound.value = false
  error.value = ''
  try {
    const { data } = await getPage(slug)
    html.value = data.html
  } catch (err) {
    html.value = ''
    if (err.response?.status === 404) notFound.value = true
    else error.value = apiErrorMessage(err)
  } finally {
    loading.value = false
  }
}

watch(() => route.params.slug, (slug) => slug && load(slug), { immediate: true })
</script>

<template>
  <div class="container my-5">
    <LoadingSpinner v-if="loading" />
    <div v-else-if="notFound" data-testid="page-not-found" class="text-muted">Page not found.</div>
    <div v-else-if="error" class="alert alert-danger" data-testid="page-error">{{ error }}</div>
    <!-- pages/<slug>.html is admin-authored HTML from $CLOUDGENE_HOME/pages -->
    <div v-else data-testid="page-content" v-html="html"></div>
  </div>
</template>
