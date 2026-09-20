<script setup>
import { useServerStore } from '@/stores/server'

const server = useServerStore()
</script>

<template>
  <div
    v-if="server.maintenance"
    class="alert alert-warning rounded-0 mb-0 text-center"
    role="status"
    data-testid="maintenance-banner"
  >
    <i class="fas fa-tools me-2"></i>{{ server.maintenanceMessage }}
  </div>
</template>
