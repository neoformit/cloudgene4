import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { onUnauthorized } from '@/api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // Public
    { path: '/', component: () => import('@/views/public/HomeView.vue') },
    { path: '/login', component: () => import('@/views/public/LoginView.vue') },
    { path: '/register', component: () => import('@/views/public/RegisterView.vue') },
    { path: '/activate/:key', component: () => import('@/views/public/ActivateView.vue') },
    { path: '/reset-password', component: () => import('@/views/public/PasswordResetView.vue') },
    { path: '/recover/:token', component: () => import('@/views/public/PasswordRecoveryView.vue') },
    { path: '/pages/:slug', component: () => import('@/views/public/StaticPageView.vue') },

    // Auth required
    {
      path: '/profile',
      component: () => import('@/views/public/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/jobs',
      component: () => import('@/views/public/JobListView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/jobs/:id',
      component: () => import('@/views/public/JobDetailView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/run/:workflowId',
      component: () => import('@/views/public/WorkflowSubmitView.vue'),
      meta: { requiresAuth: true },
    },

    // Admin required
    {
      path: '/admin',
      component: () => import('@/views/admin/AdminDashboardView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/jobs',
      component: () => import('@/views/admin/AdminJobsView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/users',
      component: () => import('@/views/admin/AdminUsersView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/workflows',
      component: () => import('@/views/admin/AdminWorkflowsView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/workflows/:id',
      component: () => import('@/views/admin/AdminWorkflowSettingsView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/settings/general',
      component: () => import('@/views/admin/settings/GeneralSettingsView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/settings/nextflow',
      component: () => import('@/views/admin/settings/NextflowSettingsView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/settings/mail',
      component: () => import('@/views/admin/settings/MailSettingsView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/settings/pages',
      component: () => import('@/views/admin/settings/PagesView.vue'),
      meta: { requiresAdmin: true },
    },
    { path: '/admin/settings/templates', redirect: '/admin/settings/pages' },
    {
      path: '/admin/settings/logs',
      component: () => import('@/views/admin/settings/LogsView.vue'),
      meta: { requiresAdmin: true },
    },

    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// --- Guards (T01): wait for the session to be known, then check meta flags.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.boot()

  const login = { path: '/login', query: { next: to.fullPath } }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return auth.isLoggedIn ? '/' : login
  }
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return login
  }
})

// A 401 means the session is gone (expired / logged out elsewhere). Reset the store and
// leave protected pages; anonymous-allowed pages just see the rejected request.
onUnauthorized(() => {
  const auth = useAuthStore()
  if (!auth.user) return
  auth._clear()
  const current = router.currentRoute.value
  if (current.meta.requiresAuth || current.meta.requiresAdmin) {
    router.push({ path: '/login', query: { next: current.fullPath } })
  }
})

export default router
