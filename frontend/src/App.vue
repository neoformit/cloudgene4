<script setup>
import { onMounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useServerStore } from '@/stores/server'
import AppNavbar from '@/components/layout/AppNavbar.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import MaintenanceBanner from '@/components/layout/MaintenanceBanner.vue'

const auth = useAuthStore()
const server = useServerStore()

onMounted(() => server.load())

// The navbar returned by /api/server is filtered for the viewer: refresh on login/logout.
watch(
  () => auth.user?.id ?? null,
  (now, before) => {
    if (now !== before) server.load(true)
  }
)
</script>

<template>
  <AppNavbar />
  <MaintenanceBanner />
  <RouterView />
  <AppFooter />
</template>
