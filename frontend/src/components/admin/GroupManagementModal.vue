<template>
  <div class="modal fade" :class="{ show: show }" :style="{ display: show ? 'block' : 'none' }" @click="closeIfBackdrop">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-users me-2"></i>
            Group Management
          </h5>
          <button type="button" class="btn-close" @click="$emit('close')"></button>
        </div>
        
        <div class="modal-body">
          <AlertMessage :message="error" />
          
          <div v-if="success" class="alert alert-success">
            {{ success }}
          </div>
          
          <!-- Create New Group Section -->
          <div class="card mb-4">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="fas fa-plus me-2"></i>
                Create New Group
              </h6>
            </div>
            <div class="card-body">
              <form @submit.prevent="createGroup">
                <div class="row">
                  <div class="col-md-8">
                    <input
                      v-model="newGroupName"
                      type="text"
                      class="form-control"
                      placeholder="Group name (e.g., researchers, admins)"
                      :disabled="creating"
                      required
                    />
                  </div>
                  <div class="col-md-4">
                    <button type="submit" class="btn btn-primary w-100" :disabled="creating || !newGroupName.trim()">
                      <span v-if="creating" class="spinner-border spinner-border-sm me-2"></span>
                      {{ creating ? 'Creating...' : 'Create Group' }}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          </div>
          
          <!-- Existing Groups Section -->
          <div class="card">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="fas fa-list me-2"></i>
                Existing Groups
              </h6>
            </div>
            <div class="card-body p-0" v-if="groups.length">
              <div class="table-responsive">
                <table class="table table-sm mb-0">
                  <thead>
                    <tr>
                      <th>Group Name</th>
                      <th class="text-center">Members</th>
                      <th class="text-end">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="group in groups" :key="group.id">
                      <td>
                        <strong>{{ group.name }}</strong>
                      </td>
                      <td class="text-center">
                        <span class="badge bg-primary">
                          {{ getUserCount(group.name) }}
                        </span>
                      </td>
                      <td class="text-end">
                        <button
                          class="btn btn-sm btn-outline-primary me-2"
                          @click="viewGroupMembers(group)"
                          title="View members"
                        >
                          <i class="fas fa-users"></i>
                        </button>
                        <button
                          class="btn btn-sm btn-outline-danger"
                          @click="confirmDeleteGroup = group"
                          title="Delete group"
                          :disabled="getUserCount(group.name) > 0"
                        >
                          <i class="fas fa-trash"></i>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div v-else class="card-body text-center text-muted">
              No groups created yet.
            </div>
          </div>
        </div>
        
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="$emit('close')">
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
  
  <!-- Group Members Modal -->
  <GroupMembersModal 
    v-if="selectedGroup"
    :group="selectedGroup"
    :users="users"
    @close="selectedGroup = null"
    @update="handleMembersUpdate"
  />
  
  <!-- Delete Group Confirmation -->
  <ConfirmDialog
    v-if="confirmDeleteGroup"
    title="Delete Group"
    :message="`Are you sure you want to delete the group <b>${confirmDeleteGroup.name}</b>? This action cannot be undone.`"
    confirm-text="Delete Group"
    :loading="deleting"
    @confirm="deleteGroup"
    @cancel="confirmDeleteGroup = null"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { createGroup as createGroupApi, deleteGroup as deleteGroupApi, listGroups } from '@/api/users'
import AlertMessage from '@/components/common/AlertMessage.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import GroupMembersModal from './GroupMembersModal.vue'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  users: {
    type: Array,
    default: () => []
  },
  initialGroups: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close', 'groupsUpdated'])

const groups = ref([...props.initialGroups])
const newGroupName = ref('')
const creating = ref(false)
const deleting = ref(false)
const error = ref('')
const success = ref('')
const selectedGroup = ref(null)
const confirmDeleteGroup = ref(null)

const getUserCount = (groupName) => {
  return props.users.filter(user => 
    (user.groups || []).includes(groupName)
  ).length
}

const closeIfBackdrop = (event) => {
  if (event.target === event.currentTarget) {
    emit('close')
  }
}

const refreshGroups = async () => {
  try {
    const response = await listGroups()
    groups.value = response.data.results || response.data || []
  } catch (err) {
    console.error('Failed to refresh groups:', err)
  }
}

const createGroup = async () => {
  if (!newGroupName.value.trim()) return
  
  creating.value = true
  error.value = ''
  success.value = ''
  
  try {
    const response = await createGroupApi({
      name: newGroupName.value.trim()
    })
    
    groups.value.push(response.data)
    newGroupName.value = ''
    success.value = `Group "${response.data.name}" created successfully`
    emit('groupsUpdated')
    
    // Clear success message after 3 seconds
    setTimeout(() => {
      success.value = ''
    }, 3000)
  } catch (err) {
    error.value = err.response?.data?.message || 'Failed to create group'
  } finally {
    creating.value = false
  }
}

const viewGroupMembers = (group) => {
  selectedGroup.value = group
}

const deleteGroup = async () => {
  if (!confirmDeleteGroup.value) return
  
  deleting.value = true
  error.value = ''
  
  try {
    await deleteGroupApi(confirmDeleteGroup.value.id)
    groups.value = groups.value.filter(g => g.id !== confirmDeleteGroup.value.id)
    success.value = `Group "${confirmDeleteGroup.value.name}" deleted successfully`
    emit('groupsUpdated')
    
    // Clear success message after 3 seconds
    setTimeout(() => {
      success.value = ''
    }, 3000)
  } catch (err) {
    error.value = err.response?.data?.message || 'Failed to delete group'
  } finally {
    deleting.value = false
    confirmDeleteGroup.value = null
  }
}

const handleMembersUpdate = () => {
  emit('groupsUpdated')
}

onMounted(() => {
  if (props.show) {
    refreshGroups()
  }
})
</script>

<style scoped>
.modal.show {
  background-color: rgba(0, 0, 0, 0.5);
}
</style>