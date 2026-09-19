<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useServerStore } from '@/stores/server'

const route = useRoute()
const server = useServerStore()

const pageHtml = computed(() => server.templates[route.params.slug] || '')
</script>

<template>
  <div class="container my-5">
    <div v-if="pageHtml" data-testid="page-content" v-html="pageHtml"></div>
    <div v-else data-testid="page-not-found" class="text-muted">Page not found.</div>
  </div>
</template>
