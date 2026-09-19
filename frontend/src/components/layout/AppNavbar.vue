<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useServerStore } from '@/stores/server'

const auth = useAuthStore()
const server = useServerStore()
const router = useRouter()

const publicNavItems = computed(() =>
  server.navbarItems.filter((i) => !i.admin_only)
)

async function logout() {
  await auth.logout()
  router.push('/')
}
</script>

<template>
  <nav data-testid="navbar" class="navbar navbar-expand-md fixed-top navbar-dark bg-dark">
    <div class="container">
      <RouterLink class="navbar-brand" to="/" data-testid="nav-brand">Cloudgene</RouterLink>
      <button
        class="navbar-toggler"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#mainNav"
        aria-controls="mainNav"
        aria-expanded="false"
        aria-label="Toggle navigation"
      >
        <span class="navbar-toggler-icon"></span>
      </button>

      <div class="collapse navbar-collapse" id="mainNav">
        <ul class="navbar-nav me-auto">
          <li class="nav-item">
            <RouterLink class="nav-link" to="/" data-testid="nav-home">Home</RouterLink>
          </li>

          <li class="nav-item" v-if="auth.isLoggedIn">
            <RouterLink class="nav-link" to="/jobs" data-testid="nav-jobs">Jobs</RouterLink>
          </li>

          <li
            v-for="item in publicNavItems"
            :key="item.id"
            class="nav-item"
          >
            <a class="nav-link" data-testid="nav-item" :href="item.url" :target="item.url?.startsWith('http') ? '_blank' : undefined">
              {{ item.title }}
            </a>
          </li>
        </ul>

        <ul class="navbar-nav">
          <template v-if="auth.isLoggedIn">
            <li class="nav-item dropdown">
              <a
                class="nav-link dropdown-toggle"
                data-testid="nav-user-menu"
                href="#"
                data-bs-toggle="dropdown"
                aria-expanded="false"
              >
                <i class="fas fa-user me-1"></i>{{ auth.user?.username }}
              </a>
              <ul class="dropdown-menu dropdown-menu-end">
                <li>
                  <RouterLink class="dropdown-item" to="/profile" data-testid="nav-profile">Profile</RouterLink>
                </li>
                <li><hr class="dropdown-divider" /></li>
                <li v-if="auth.isAdmin">
                  <RouterLink class="dropdown-item" to="/admin" data-testid="nav-admin">Admin Panel</RouterLink>
                </li>
                <li v-if="auth.isAdmin"><hr class="dropdown-divider" /></li>
                <li>
                  <button class="dropdown-item" data-testid="nav-logout" @click="logout">Logout</button>
                </li>
              </ul>
            </li>
          </template>
          <template v-else>
            <li class="nav-item">
              <RouterLink class="nav-link" to="/register" data-testid="nav-signup">Sign up</RouterLink>
            </li>
            <li class="nav-item">
              <RouterLink class="nav-link" to="/login" data-testid="nav-login">Login</RouterLink>
            </li>
          </template>
        </ul>
      </div>
    </div>
  </nav>
</template>
