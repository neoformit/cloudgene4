<script setup>
/** Steps → per-Nextflow-process task counts, plus job messages (SPEC §3.3 progress). */
import { computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  messages: { type: Array, default: () => [] },
})

const levelClass = {
  info: 'text-body',
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-danger',
  debug: 'text-muted',
}
const levelIcon = {
  info: 'fas fa-info-circle text-info',
  success: 'fas fa-check-circle text-success',
  warning: 'fas fa-exclamation-triangle text-warning',
  error: 'fas fa-times-circle text-danger',
  debug: 'fas fa-bug text-muted',
}
const stepIcon = {
  waiting: 'far fa-circle text-muted',
  running: 'fas fa-spinner fa-spin text-primary',
  success: 'fas fa-check text-success',
  failed: 'fas fa-times text-danger',
  cancelled: 'fas fa-ban text-warning',
}

const messagesByStep = computed(() => {
  const map = { none: [] }
  for (const m of props.messages) {
    const key = m.step ?? 'none'
    ;(map[key] ||= []).push(m)
  }
  return map
})

function percent(proc) {
  if (!proc.total) return 0
  return Math.round(((proc.completed + proc.failed) / proc.total) * 100)
}
</script>

<template>
  <div data-testid="job-progress">
    <div v-for="m in messagesByStep.none" :key="`m-${m.id}`" class="mb-2"
         data-testid="job-message" :data-level="m.level">
      <i :class="levelIcon[m.level]" class="me-2"></i>
      <span :class="levelClass[m.level]" style="white-space: pre-wrap">{{ m.text }}</span>
    </div>

    <div v-for="step in steps" :key="step.id" class="card mb-3" data-testid="job-step" :data-state="step.state">
      <div class="card-header d-flex align-items-center">
        <i :class="stepIcon[step.state] || 'far fa-circle'" class="me-2"></i>
        <strong data-testid="job-step-name">{{ step.name }}</strong>
      </div>
      <div class="card-body">
        <div v-if="!step.processes.length && step.state === 'running'" class="text-muted small">
          Running…
        </div>
        <div v-for="proc in step.processes" :key="proc.name" class="mb-2" data-testid="job-process"
             :data-process="proc.name" :data-completed="proc.completed" :data-total="proc.total"
             :data-failed="proc.failed" :data-running="proc.running">
          <div class="d-flex justify-content-between small">
            <span class="fw-semibold">{{ proc.label || proc.name }}</span>
            <span data-testid="job-process-counts">
              {{ proc.completed }} / {{ proc.total }} tasks
              <span v-if="proc.running" class="text-primary ms-1">({{ proc.running }} running)</span>
              <span v-if="proc.failed" class="text-danger ms-1">({{ proc.failed }} failed)</span>
            </span>
          </div>
          <div class="progress" style="height: 6px">
            <div class="progress-bar bg-success" :style="{ width: `${percent(proc)}%` }"></div>
          </div>
        </div>
        <div v-for="m in messagesByStep[step.id] || []" :key="`m-${m.id}`" class="mt-2"
             data-testid="job-message" :data-level="m.level">
          <i :class="levelIcon[m.level]" class="me-2"></i>
          <span :class="levelClass[m.level]" style="white-space: pre-wrap">{{ m.text }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
