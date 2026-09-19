<script setup>
import { useServerStore } from '@/stores/server'

const server = useServerStore()
</script>

<template>
  <footer data-testid="footer" class="text-muted mt-5" style="border-top: 1px solid #dee2e6;">
    <div class="container py-3">
      <p class="float-end mb-0">
        <small><a href="#">Back to top</a></small>
      </p>
      <!-- footer.html is admin-authored HTML from $CLOUDGENE_HOME/pages -->
      <div v-if="server.footerHtml" class="small" v-html="server.footerHtml"></div>
      <small v-else>Powered by Cloudgene</small>
    </div>
  </footer>
</template>
