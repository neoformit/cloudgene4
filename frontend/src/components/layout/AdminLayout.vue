<script setup>
import AdminSidebar from './AdminSidebar.vue'
</script>

<template>
  <!-- Rendered below the global AppNavbar (App.vue), so admins keep the site navigation. -->
  <div class="d-flex" style="min-height: calc(100vh - 70px);">
    <AdminSidebar />
    <main class="flex-grow-1 p-4 bg-white" data-testid="admin-main" style="min-width: 0;">
      <slot />
    </main>
  </div>
</template>
