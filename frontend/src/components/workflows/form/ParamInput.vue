<script setup>
import { computed } from 'vue'
import { isFolder, isTerms, isUpload, formatBytes } from './formModel'

const props = defineProps({
  param: { type: Object, required: true },
  modelValue: { default: null },
  error: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const p = computed(() => props.param)
const inputId = computed(() => `param-${p.value.id}`)
const helpIsLink = computed(() => /^https?:\/\//.test(p.value.help || ''))
const files = computed(() => (Array.isArray(props.modelValue) ? props.modelValue : []))
const invalid = computed(() => (props.error ? 'is-invalid' : ''))

function set(value) {
  emit('update:modelValue', value)
}

function onFiles(event) {
  set(Array.from(event.target.files || []))
}

function removeFile(index) {
  const next = files.value.slice()
  next.splice(index, 1)
  set(next)
}
</script>

<template>
  <div class="mb-3 param-input" :class="`param-${p.type}`">
    <!-- checkbox & terms: label next to the box -->
    <div v-if="p.type === 'checkbox' || isTerms(p)" class="form-check">
      <input
        :id="inputId"
        class="form-check-input"
        :class="invalid"
        type="checkbox"
        :checked="!!modelValue"
        :disabled="disabled"
        @change="set($event.target.checked)"
      />
      <label class="form-check-label" :for="inputId">
        <span v-html="p.label"></span>
        <span v-if="isTerms(p) && p.required !== false" class="text-danger ms-1" title="Required">*</span>
      </label>
      <a v-if="helpIsLink" :href="p.help" target="_blank" rel="noopener" class="ms-1" title="Help">
        <i class="fas fa-question-circle"></i>
      </a>
      <div v-if="p.details" class="form-text">{{ p.details }}</div>
      <div v-if="error" class="invalid-feedback d-block" :data-testid="`error-${p.id}`">{{ error }}</div>
    </div>

    <template v-else>
      <label class="form-label fw-semibold" :for="inputId">
        <span v-html="p.label"></span>
        <span v-if="p.required" class="text-danger ms-1" title="Required">*</span>
        <a v-if="helpIsLink" :href="p.help" target="_blank" rel="noopener" class="ms-1" title="Help">
          <i class="fas fa-question-circle"></i>
        </a>
      </label>

      <input
        v-if="p.type === 'text' || p.type === 'string'"
        :id="inputId"
        type="text"
        class="form-control"
        :class="invalid"
        :value="modelValue"
        :required="p.required"
        :disabled="disabled"
        @input="set($event.target.value)"
      />

      <input
        v-else-if="p.type === 'number'"
        :id="inputId"
        type="number"
        step="any"
        class="form-control"
        :class="invalid"
        :value="modelValue"
        :min="p.min ?? undefined"
        :max="p.max ?? undefined"
        :required="p.required"
        :disabled="disabled"
        @input="set($event.target.value)"
      />

      <textarea
        v-else-if="p.type === 'textarea'"
        :id="inputId"
        class="form-control"
        :class="invalid"
        rows="5"
        :value="modelValue"
        :required="p.required"
        :disabled="disabled"
        @input="set($event.target.value)"
      ></textarea>

      <select
        v-else-if="p.type === 'list'"
        :id="inputId"
        class="form-select"
        :class="invalid"
        :value="modelValue"
        :required="p.required"
        :disabled="disabled"
        @change="set($event.target.value)"
      >
        <option v-if="!p.required || !modelValue" value="">— select —</option>
        <option v-for="o in p.values" :key="o.key" :value="o.key">{{ o.label }}</option>
      </select>

      <div v-else-if="p.type === 'radio'" :id="inputId" role="radiogroup">
        <div v-for="o in p.values" :key="o.key" class="form-check form-check-inline">
          <input
            :id="`${inputId}-${o.key}`"
            class="form-check-input"
            :class="invalid"
            type="radio"
            :name="inputId"
            :value="o.key"
            :checked="modelValue === o.key"
            :disabled="disabled"
            @change="set(o.key)"
          />
          <label class="form-check-label" :for="`${inputId}-${o.key}`">{{ o.label }}</label>
        </div>
      </div>

      <div v-else-if="isUpload(p)">
        <input
          :id="inputId"
          type="file"
          class="form-control"
          :class="invalid"
          :multiple="isFolder(p)"
          :accept="p.accept || undefined"
          :disabled="disabled"
          @change="onFiles"
        />
        <ul v-if="files.length" class="list-unstyled small mt-1 mb-0" :data-testid="`files-${p.id}`">
          <li v-for="(f, i) in files" :key="`${f.name}-${i}`">
            <i class="fas fa-file me-1 text-muted"></i>{{ f.name }}
            <span class="text-muted">({{ formatBytes(f.size) }})</span>
            <button type="button" class="btn btn-link btn-sm p-0 ms-2" title="Remove" @click="removeFile(i)">
              <i class="fas fa-times"></i>
            </button>
          </li>
        </ul>
      </div>

      <div v-if="p.help && !helpIsLink" class="form-text">{{ p.help }}</div>
      <div v-if="p.details" class="form-text">{{ p.details }}</div>
      <div v-if="p.accept && isUpload(p)" class="form-text">Accepted: {{ p.accept }}</div>
      <div v-if="error" class="invalid-feedback d-block" :data-testid="`error-${p.id}`">{{ error }}</div>
    </template>
  </div>
</template>
