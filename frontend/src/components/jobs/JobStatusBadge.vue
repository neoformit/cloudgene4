<script setup>
import { computed } from 'vue'

// `state` (SPEC name) or legacy `status`.
const props = defineProps({
  state: { type: String, default: '' },
  status: { type: String, default: '' },
  withLabel: { type: Boolean, default: false },
  testid: { type: String, default: 'job-state' },
})

const value = computed(() => props.state || props.status || 'unknown')

const icons = {
  waiting: 'fas fa-hourglass-half',
  running: 'fas fa-spinner fa-spin',
  success: 'fas fa-check',
  failed: 'fas fa-times',
  cancelled: 'fas fa-ban',
}
const labels = {
  waiting: 'Waiting',
  running: 'Running',
  success: 'Success',
  failed: 'Failed',
  cancelled: 'Cancelled',
}
const classes = {
  waiting: 'bg-secondary',
  running: 'bg-primary',
  success: 'bg-success',
  failed: 'bg-danger',
  cancelled: 'bg-warning text-dark',
}
</script>

<template>
  <span
    :data-testid="testid"
    :data-state="value"
    :title="labels[value] || value"
    :class="['badge', classes[value] || 'bg-light text-dark']"
  >
    <i :class="icons[value] || 'fas fa-circle'"></i>
    <span v-if="withLabel" class="ms-1">{{ labels[value] || value }}</span>
  </span>
</template>
