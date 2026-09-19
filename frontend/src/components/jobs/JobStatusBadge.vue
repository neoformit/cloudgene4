<script setup>
defineProps({ status: { type: String, required: true } })

const icons = {
  pending: 'fas fa-clock',
  waiting: 'fas fa-hourglass-half',
  running: 'fas fa-spinner fa-spin',
  completed: 'fas fa-check',
  failed: 'fas fa-times',
  cancelled: 'fas fa-ban',
}

const labels = {
  pending: 'Pending',
  waiting: 'Waiting',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}
</script>

<template>
  <span data-testid="job-state" :data-state="status" :class="`badge badge-${status} status-xs`">
    <i :class="icons[status] || 'fas fa-circle'"></i>
  </span>
</template>
