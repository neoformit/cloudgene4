<script setup>
/**
 * Renders every SPEC §4 input type. Values live in the parent (v-model); `errors` maps
 * input id → message (client validation or server `error.fields`).
 */
import ParamInput from './ParamInput.vue'
import { isDisplay } from './formModel'

defineProps({
  params: { type: Array, required: true },
  modelValue: { type: Object, required: true },
  errors: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

function update(values, id, value) {
  emit('update:modelValue', { ...values, [id]: value })
}
</script>

<template>
  <div data-testid="dynamic-form">
    <template v-for="param in params" :key="param.id">
      <hr v-if="param.type === 'separator'" :data-testid="`input-${param.id}`" class="my-4" />
      <div
        v-else-if="param.type === 'info'"
        :data-testid="`input-${param.id}`"
        class="alert alert-info"
        v-html="param.label"
      ></div>
      <p
        v-else-if="param.type === 'label'"
        :data-testid="`input-${param.id}`"
        class="text-muted"
        v-html="param.label"
      ></p>
      <div
        v-else-if="!isDisplay(param) && param.visible !== false"
        :data-testid="`input-${param.id}`"
        :data-type="param.type"
      >
        <ParamInput
          :param="param"
          :model-value="modelValue[param.id]"
          :error="errors[param.id] || ''"
          :disabled="disabled"
          @update:model-value="update(modelValue, param.id, $event)"
        />
      </div>
    </template>
  </div>
</template>
