<script setup>
import { ref, onMounted } from 'vue'
import { createGroup, deleteGroup, listGroups } from '@/api/users'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import { firstFieldErrors, validateGroupName } from '@/utils/validation'
import AlertMessage from '@/components/common/AlertMessage.vue'
import GroupMembersModal from './GroupMembersModal.vue'

defineProps({
  show: { type: Boolean, default: true },
})
const emit = defineEmits(['close', 'groups-updated'])

const PROTECTED = 'admin'

const groups = ref([])
const loading = ref(true)
const error = ref('')
const nameError = ref('')
const newGroupName = ref('')
const creating = ref(false)
const confirmDelete = ref(null)
const deleting = ref(false)
const selectedGroup = ref(null)

async function refresh() {
  loading.value = true
  try {
    const { data } = await listGroups()
    groups.value = data
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load groups.')
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function create() {
  error.value = ''
  nameError.value = validateGroupName(newGroupName.value) || ''
  if (nameError.value) return
  creating.value = true
  try {
    await createGroup({ name: newGroupName.value.trim() })
    newGroupName.value = ''
    await refresh()
    emit('groups-updated')
  } catch (e) {
    nameError.value = firstFieldErrors(apiFieldErrors(e)).name || ''
    if (!nameError.value) error.value = apiErrorMessage(e, 'Creating the group failed.')
  } finally {
    creating.value = false
  }
}

async function doDelete() {
  deleting.value = true
  error.value = ''
  try {
    await deleteGroup(confirmDelete.value.id)
    confirmDelete.value = null
    await refresh()
    emit('groups-updated')
  } catch (e) {
    error.value = apiErrorMessage(e, 'Deleting the group failed.')
    confirmDelete.value = null
  } finally {
    deleting.value = false
  }
}

function membersChanged() {
  refresh()
  emit('groups-updated')
}
</script>

<template>
  <div
    class="modal d-block"
    tabindex="-1"
    style="background: rgba(0,0,0,0.5);"
    data-testid="group-modal"
    @click.self="emit('close')"
  >
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-users me-2"></i>Groups</h5>
          <button type="button" class="btn-close" aria-label="Close" data-testid="group-modal-close-x" @click="emit('close')"></button>
        </div>

        <div class="modal-body">
          <p class="text-muted small">
            Groups control which workflows a user may run. Administrator rights are managed with the
            “Make admin” button in the user list, not through the <code>admin</code> group here.
          </p>
          <AlertMessage :message="error" data-testid="group-error" />

          <form class="d-flex gap-2 mb-4" novalidate data-testid="group-create-form" @submit.prevent="create">
            <div class="flex-grow-1">
              <input
                v-model="newGroupName"
                type="text"
                :class="['form-control', nameError ? 'is-invalid' : '']"
                placeholder="New group name, e.g. researchers"
                aria-label="New group name"
                :disabled="creating"
                data-testid="group-create-name"
              />
              <div class="invalid-feedback" data-testid="group-create-error">{{ nameError }}</div>
            </div>
            <div>
              <button type="submit" class="btn btn-primary text-nowrap" :disabled="creating" data-testid="group-create-submit">
                <span v-if="creating" class="spinner-border spinner-border-sm me-1"></span>
                Create group
              </button>
            </div>
          </form>

          <div v-if="loading" class="text-muted">Loading…</div>
          <table v-else-if="groups.length" class="table table-sm align-middle mb-0" data-testid="group-table">
            <thead>
              <tr>
                <th>Group</th>
                <th class="text-center">Members</th>
                <th class="text-end">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="group in groups" :key="group.id" data-testid="group-row" :data-group="group.name">
                <td><strong>{{ group.name }}</strong></td>
                <td class="text-center">
                  <span class="badge bg-primary" data-testid="group-member-count">{{ group.member_count }}</span>
                </td>
                <td class="text-end text-nowrap">
                  <button
                    class="btn btn-sm btn-outline-primary me-2"
                    title="Members"
                    :aria-label="`Members of ${group.name}`"
                    data-testid="group-members"
                    @click="selectedGroup = group"
                  >
                    <i class="fas fa-users"></i>
                  </button>
                  <button
                    class="btn btn-sm btn-outline-danger"
                    :title="group.name === PROTECTED ? 'The admin group cannot be deleted' : 'Delete group'"
                    :aria-label="`Delete ${group.name}`"
                    :disabled="group.name === PROTECTED"
                    data-testid="group-delete"
                    @click="confirmDelete = group"
                  >
                    <i class="fas fa-trash"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="text-center text-muted" data-testid="group-empty">No groups yet.</div>

          <div v-if="confirmDelete" class="alert alert-danger mt-3" data-testid="group-delete-dialog">
            Delete group <strong>{{ confirmDelete.name }}</strong>?
            Its {{ confirmDelete.member_count }} member(s) lose access to workflows restricted to it.
            <div class="mt-2">
              <button class="btn btn-sm btn-danger me-2" :disabled="deleting" data-testid="group-delete-confirm" @click="doDelete">
                Delete
              </button>
              <button class="btn btn-sm btn-secondary" :disabled="deleting" data-testid="group-delete-cancel" @click="confirmDelete = null">
                Cancel
              </button>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-testid="group-modal-close" @click="emit('close')">Close</button>
        </div>
      </div>
    </div>
  </div>

  <GroupMembersModal
    v-if="selectedGroup"
    :group="selectedGroup"
    @close="selectedGroup = null"
    @members-changed="membersChanged"
  />
</template>
