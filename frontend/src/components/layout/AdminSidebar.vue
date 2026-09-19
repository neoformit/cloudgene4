<script setup>
// Every link here must have a route in src/router/index.js (F7).
const sections = [
  {
    items: [
      { to: '/admin', icon: 'tachometer-alt', label: 'Dashboard', id: 'dashboard', exact: true },
      { to: '/admin/jobs', icon: 'tasks', label: 'Jobs', id: 'jobs' },
      { to: '/admin/users', icon: 'users', label: 'Users', id: 'users' },
      { to: '/admin/workflows', icon: 'sitemap', label: 'Workflows', id: 'workflows' },
    ],
  },
  {
    title: 'Settings',
    items: [
      { to: '/admin/settings/general', icon: 'cog', label: 'General', id: 'general' },
      { to: '/admin/settings/nextflow', icon: 'stream', label: 'Nextflow', id: 'nextflow' },
      { to: '/admin/settings/pages', icon: 'file-code', label: 'Pages', id: 'pages' },
      { to: '/admin/settings/mail', icon: 'envelope', label: 'Mail', id: 'mail' },
      { to: '/admin/settings/logs', icon: 'scroll', label: 'Logs', id: 'logs' },
    ],
  },
]
</script>

<template>
  <nav class="admin-sidebar d-flex flex-column p-3 border-end bg-light" style="min-width: 210px;" data-testid="admin-sidebar">
    <ul class="nav flex-column">
      <template v-for="(section, si) in sections" :key="si">
        <li v-if="section.title" class="nav-item mt-3 mb-1">
          <small class="text-muted text-uppercase ps-2 fw-semibold" style="font-size: 0.7rem;">{{ section.title }}</small>
        </li>
        <li v-for="item in section.items" :key="item.to" class="nav-item mb-1">
          <RouterLink
            class="nav-link"
            :to="item.to"
            :exact-active-class="item.exact ? 'active fw-semibold' : ''"
            :active-class="item.exact ? '' : 'active fw-semibold'"
            :data-testid="`admin-nav-${item.id}`"
          >
            <i :class="`fas fa-${item.icon} me-1`"></i> {{ item.label }}
          </RouterLink>
        </li>
      </template>
    </ul>
  </nav>
</template>
