<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useServerStore } from '@/stores/server'

const auth = useAuthStore()
const server = useServerStore()
const router = useRouter()

// Items come from settings.yaml `navbar:` via /api/server (already filtered for the viewer).
// The backend validates url (C-05: an internal path or an http(s) URL) but the frontend
// never trusts that alone — only those two shapes are ever rendered as a link.
const isExternal = (url) => /^https?:\/\//i.test(url || '')
const isInternal = (url) => (url || '').startsWith('/')

async function logout() {
  await auth.logout()
  router.push('/')
}
</script>

<template>
  <nav data-testid="navbar" class="navbar navbar-expand-md fixed-top navbar-dark bg-dark">
    <div class="container">
      <RouterLink class="navbar-brand" to="/" data-testid="nav-brand">{{ server.name }}</RouterLink>
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
          <li v-for="(item, i) in server.navbar" :key="`${i}-${item.url}`" class="nav-item">
            <a
              v-if="isExternal(item.url)"
              class="nav-link"
              data-testid="nav-item"
              :href="item.url"
              target="_blank"
              rel="noopener"
            >
              <i v-if="item.icon" :class="`fas fa-${item.icon} me-1`"></i>{{ item.title }}
            </a>
            <RouterLink v-else-if="isInternal(item.url)" class="nav-link" data-testid="nav-item"
                       :to="item.url">
              <i v-if="item.icon" :class="`fas fa-${item.icon} me-1`"></i>{{ item.title }}
            </RouterLink>
            <span v-else class="nav-link disabled" data-testid="nav-item">
              <i v-if="item.icon" :class="`fas fa-${item.icon} me-1`"></i>{{ item.title }}
            </span>
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
                  <RouterLink class="dropdown-item" to="/jobs" data-testid="nav-jobs">My Jobs</RouterLink>
                </li>
                <li>
                  <RouterLink class="dropdown-item" to="/profile" data-testid="nav-profile">Profile</RouterLink>
                </li>
                <li v-if="auth.isAdmin"><hr class="dropdown-divider" /></li>
                <li v-if="auth.isAdmin">
                  <RouterLink class="dropdown-item" to="/admin" data-testid="nav-admin">Admin Panel</RouterLink>
                </li>
                <li><hr class="dropdown-divider" /></li>
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
