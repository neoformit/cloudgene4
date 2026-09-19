<script setup>
import { reactive } from 'vue'
import TextInput from './TextInput.vue'
import TextareaInput from './TextareaInput.vue'
import SelectInput from './SelectInput.vue'
import RadioInput from './RadioInput.vue'
import CheckboxInput from './CheckboxInput.vue'
import TermsInput from './TermsInput.vue'
import FileInput from './FileInput.vue'

const props = defineProps({
  params: { type: Array, required: true },
  workflowId: { type: String, required: true },
  jobName: { type: String, required: true },
})
const emit = defineEmits(['submit'])

// Expose onSubmit method for parent component access
defineExpose({ onSubmit })

const values = reactive({})

// Seed defaults
for (const p of props.params) {
  if (p.type === 'checkbox' || p.type === 'agb_checkbox' || p.type === 'terms_checkbox') {
    values[p.id] = false
  } else {
    values[p.id] = p.value ?? ''
  }
}

function onSubmit() {
  const formData = new FormData()
  
  // Add workflow and job metadata
  formData.append('workflow_id', props.workflowId)
  formData.append('job_name', props.jobName)
  
  // Add all parameter values
  for (const p of props.params) {
    const v = values[p.id]
    if (Array.isArray(v)) {
      for (const f of v) formData.append(p.id, f)
    } else if (v instanceof File) {
      formData.append(p.id, v)
    } else if (v !== '' && v !== null && v !== undefined) {
      formData.append(p.id, v)
    }
  }
  
  emit('submit', formData)
}

const FILE_TYPES = new Set(['local_file', 'hdfs_file', 'file'])
const FOLDER_TYPES = new Set(['local_folder', 'hdfs_folder', 'folder'])
const TEXT_TYPES = new Set(['text', 'number', 'string'])
</script>

<template>
  <div>
    <template v-for="param in params" :key="param.id">
      <template v-if="param.type === 'separator'">
        <hr :data-testid="`input-${param.id}`" />
      </template>
      <template v-else-if="param.type === 'info' || param.type === 'label'">
        <p :data-testid="`input-${param.id}`" class="text-muted" v-html="param.label"></p>
      </template>
      <template v-else-if="TEXT_TYPES.has(param.type)">
        <TextInput :data-testid="`input-${param.id}`" :param="param" v-model="values[param.id]" />
      </template>
      <template v-else-if="param.type === 'textarea'">
        <TextareaInput :data-testid="`input-${param.id}`" :param="param" v-model="values[param.id]" />
      </template>
      <template v-else-if="param.type === 'list' || param.type === 'binded_list' || param.type === 'app_list'">
        <SelectInput :data-testid="`input-${param.id}`" :param="param" v-model="values[param.id]" />
      </template>
      <template v-else-if="param.type === 'radio'">
        <RadioInput :data-testid="`input-${param.id}`" :param="param" v-model="values[param.id]" />
      </template>
      <template v-else-if="param.type === 'checkbox' || param.type === 'agb_checkbox'">
        <CheckboxInput :data-testid="`input-${param.id}`" :param="param" v-model="values[param.id]" />
      </template>
      <template v-else-if="param.type === 'terms_checkbox'">
        <TermsInput :data-testid="`input-${param.id}`" :param="param" v-model="values[param.id]" />
      </template>
      <template v-else-if="FILE_TYPES.has(param.type)">
        <FileInput :data-testid="`input-${param.id}`" :param="param" :multiple="false" v-model="values[param.id]" />
      </template>
      <template v-else-if="FOLDER_TYPES.has(param.type)">
        <FileInput :data-testid="`input-${param.id}`" :param="param" :multiple="true" v-model="values[param.id]" />
      </template>
    </template>
  </div>
</template>
