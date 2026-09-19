<script setup>
import { computed } from 'vue'
import { useServerStore } from '@/stores/server'

const server = useServerStore()
const footerHtml = computed(() => server.templates.footer || '')
</script>

<template>
  <footer data-testid="footer" class="text-muted mt-5" style="border-top: 1px solid #dee2e6;">
    <div class="container py-3">
      <p class="float-end mb-0">
        <small><a href="#">Back to top</a></small>
      </p>
      <p class="mb-0">
        <small v-if="footerHtml" v-html="footerHtml"></small>
        <small v-else>Powered by Cloudgene</small>
      </p>
    </div>
  </footer>
</template>
