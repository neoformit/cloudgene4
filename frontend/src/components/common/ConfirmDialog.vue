<script setup>
defineProps({
  title: { type: String, default: 'Confirm' },
  message: { type: String, required: true },
  confirmText: { type: String, default: 'Confirm' },
  confirmClass: { type: String, default: 'btn-danger' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <div class="modal d-block" tabindex="-1" style="background: rgba(0,0,0,0.5);">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">{{ title }}</h5>
          <button type="button" class="btn-close" @click="$emit('cancel')"></button>
        </div>
        <div class="modal-body" v-html="message"></div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-testid="confirm-dismiss" :disabled="loading" @click="$emit('cancel')">Cancel</button>
          <button :class="`btn ${confirmClass}`" data-testid="confirm-ok" :disabled="loading" @click="$emit('confirm')">
            <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
            {{ loading ? 'Please wait...' : confirmText }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
