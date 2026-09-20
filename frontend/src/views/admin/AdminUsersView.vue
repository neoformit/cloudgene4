<script setup>
import { computed, ref, onMounted } from 'vue'
import { deleteUser, listGroups, listUsers, updateUser } from '@/api/users'
import { apiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { avatarHue, initials } from '@/utils/avatar'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import Pagination from '@/components/common/Pagination.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'
import GroupManagementModal from '@/components/admin/GroupManagementModal.vue'

const ADMIN_GROUP = 'admin'
const PAGE_SIZE = 20

const auth = useAuthStore()
const users = ref([])
const total = ref(0)
const currentPage = ref(1)
const loading = ref(true)
const search = ref('')
const groups = ref([])
const busy = ref({}) // user id → true while a request for that row runs
const error = ref('')
const confirmUser = ref(null)
const deleting = ref(false)
const showGroupModal = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
// The admin group is managed with the "Admin" toggle, not as a chip.
const assignableGroups = computed(() => groups.value.filter((g) => g.name !== ADMIN_GROUP))

async function fetchUsers(page = 1) {
  loading.value = true
  error.value = ''
  try {
    const params = { page, page_size: PAGE_SIZE }
    if (search.value.trim()) params.search = search.value.trim()
    const { data } = await listUsers(params)
    users.value = data.results
    total.value = data.count
    currentPage.value = page
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load users.')
  } finally {
    loading.value = false
  }
}

async function fetchGroups() {
  try {
    const { data } = await listGroups()
    groups.value = data
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load groups.')
  }
}

onMounted(() => Promise.all([fetchUsers(), fetchGroups()]))

function replaceUser(updated) {
  const i = users.value.findIndex((u) => u.id === updated.id)
  if (i >= 0) users.value[i] = updated
}

async function patch(user, data, failure) {
  busy.value = { ...busy.value, [user.id]: true }
  error.value = ''
  try {
    const { data: updated } = await updateUser(user.id, data)
    replaceUser(updated)
    return updated
  } catch (e) {
    error.value = apiErrorMessage(e, failure)
    return null
  } finally {
    const { [user.id]: _, ...rest } = busy.value
    busy.value = rest
  }
}

const userGroups = (user) => user.groups.filter((g) => g !== ADMIN_GROUP)
const missingGroups = (user) => assignableGroups.value.filter((g) => !user.groups.includes(g.name))

async function addGroup(user, event) {
  const name = event.target.value
  event.target.value = ''
  if (!name) return
  if (await patch(user, { groups: [...userGroups(user), name] }, 'Adding the group failed.')) fetchGroups()
}

async function removeGroup(user, name) {
  const next = userGroups(user).filter((g) => g !== name)
  if (await patch(user, { groups: next }, 'Removing the group failed.')) fetchGroups()
}

const toggleActive = (user) =>
  patch(user, { is_active: !user.is_active }, 'Changing the account status failed.')

async function toggleAdmin(user) {
  if (await patch(user, { is_admin: !user.is_admin }, 'Changing administrator rights failed.')) fetchGroups()
}

async function doDelete() {
  deleting.value = true
  try {
    await deleteUser(confirmUser.value.id)
    confirmUser.value = null
    const page = users.value.length === 1 && currentPage.value > 1 ? currentPage.value - 1 : currentPage.value
    await Promise.all([fetchUsers(page), fetchGroups()])
  } catch (e) {
    error.value = apiErrorMessage(e, 'Delete failed.')
    confirmUser.value = null
  } finally {
    deleting.value = false
  }
}

function handleGroupsUpdated() {
  Promise.all([fetchGroups(), fetchUsers(currentPage.value)])
}

const isSelf = (user) => auth.user?.id === user.id
const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString() : '–')
</script>

<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-4">
      <h2 class="mb-0">Users <small class="text-muted fs-6" data-testid="admin-users-count">({{ total }})</small></h2>
      <div class="d-flex gap-2">
        <form class="input-group w-auto" role="search" @submit.prevent="fetchUsers(1)">
          <input
            v-model="search"
            type="search"
            class="form-control"
            placeholder="Username, name or e-mail"
            aria-label="Search users"
            data-testid="admin-users-search"
          />
          <button class="btn btn-outline-secondary" type="submit" data-testid="admin-users-search-submit">
            <i class="fas fa-search"></i>
          </button>
        </form>
        <button class="btn btn-outline-primary" data-testid="admin-users-manage-groups" @click="showGroupModal = true">
          <i class="fas fa-users-cog me-1"></i> Groups
        </button>
      </div>
    </div>

    <AlertMessage :message="error" data-testid="admin-users-error" />
    <LoadingSpinner v-if="loading" />

    <template v-else>
      <div class="card mb-3">
        <div class="card-body p-0 table-responsive">
          <table class="table table-sm table-hover mb-0 align-middle" data-testid="admin-users-table">
            <thead>
              <tr>
                <th></th>
                <th>User</th>
                <th>E-Mail</th>
                <th>Status</th>
                <th>Joined / last login</th>
                <th>Groups</th>
                <th class="text-end">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="user in users"
                :key="user.id"
                data-testid="admin-user-row"
                :data-username="user.username"
                :class="{ 'opacity-75': busy[user.id] }"
              >
                <td>
                  <span
                    class="avatar rounded-circle d-inline-flex align-items-center justify-content-center text-white fw-bold"
                    :style="{ background: `hsl(${avatarHue(user)}, 45%, 45%)` }"
                    aria-hidden="true"
                  >{{ initials(user) }}</span>
                </td>
                <td>
                  <div class="fw-semibold" data-testid="admin-user-username">{{ user.username }}</div>
                  <small class="text-muted">{{ user.full_name }}</small>
                </td>
                <td><small>{{ user.email }}</small></td>
                <td>
                  <span
                    :class="['badge me-1', user.is_active ? 'bg-success' : 'bg-secondary']"
                    data-testid="admin-user-status"
                    :data-state="user.is_active ? 'active' : 'inactive'"
                  >{{ user.is_active ? 'active' : 'inactive' }}</span>
                  <span v-if="user.is_admin" class="badge bg-danger" data-testid="admin-user-admin-badge">admin</span>
                </td>
                <td><small>{{ formatDate(user.date_joined) }}<br>{{ formatDate(user.last_login) }}</small></td>
                <td>
                  <div class="d-flex flex-wrap align-items-center gap-1" data-testid="admin-user-groups">
                    <span
                      v-for="name in userGroups(user)"
                      :key="name"
                      class="badge rounded-pill text-bg-light border d-inline-flex align-items-center"
                      data-testid="admin-user-group"
                      :data-group="name"
                    >
                      {{ name }}
                      <button
                        type="button"
                        class="btn-close btn-close-sm ms-1"
                        style="font-size: 0.55rem;"
                        :aria-label="`Remove ${user.username} from ${name}`"
                        :disabled="busy[user.id]"
                        data-testid="admin-user-group-remove"
                        @click="removeGroup(user, name)"
                      ></button>
                    </span>
                    <select
                      v-if="missingGroups(user).length"
                      class="form-select form-select-sm w-auto"
                      :aria-label="`Add ${user.username} to a group`"
                      :disabled="busy[user.id]"
                      data-testid="admin-user-group-add"
                      @change="addGroup(user, $event)"
                    >
                      <option value="">+ group</option>
                      <option v-for="g in missingGroups(user)" :key="g.id" :value="g.name">{{ g.name }}</option>
                    </select>
                  </div>
                </td>
                <td class="text-end text-nowrap">
                  <button
                    class="btn btn-sm btn-outline-secondary me-1"
                    :disabled="busy[user.id] || isSelf(user)"
                    :title="user.is_active ? 'Deactivate' : 'Activate'"
                    data-testid="admin-user-toggle-active"
                    @click="toggleActive(user)"
                  >
                    {{ user.is_active ? 'Deactivate' : 'Activate' }}
                  </button>
                  <button
                    class="btn btn-sm btn-outline-secondary me-1"
                    :disabled="busy[user.id] || isSelf(user) || (user.is_admin && user.is_superuser)"
                    data-testid="admin-user-toggle-admin"
                    @click="toggleAdmin(user)"
                  >
                    {{ user.is_admin ? 'Remove admin' : 'Make admin' }}
                  </button>
                  <button
                    class="btn btn-sm btn-outline-danger"
                    title="Delete user"
                    :aria-label="`Delete ${user.username}`"
                    :disabled="busy[user.id] || isSelf(user)"
                    data-testid="admin-user-delete"
                    @click="confirmUser = user"
                  >
                    <i class="fas fa-trash"></i>
                  </button>
                </td>
              </tr>
              <tr v-if="!users.length">
                <td colspan="7" class="text-muted text-center" data-testid="admin-users-empty">No users found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <Pagination :current-page="currentPage" :total-pages="totalPages" @change="fetchUsers" />
    </template>

    <!-- Delete confirmation (text interpolated, never v-html) -->
    <div
      v-if="confirmUser"
      class="modal d-block"
      tabindex="-1"
      style="background: rgba(0,0,0,0.5);"
      data-testid="admin-user-delete-dialog"
    >
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Delete user</h5>
            <button type="button" class="btn-close" aria-label="Close" @click="confirmUser = null"></button>
          </div>
          <div class="modal-body">
            Delete <strong>{{ confirmUser.username }}</strong> and all their jobs? This cannot be undone.
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" :disabled="deleting" data-testid="admin-user-delete-cancel" @click="confirmUser = null">
              Cancel
            </button>
            <button class="btn btn-danger" :disabled="deleting" data-testid="admin-user-delete-confirm" @click="doDelete">
              <span v-if="deleting" class="spinner-border spinner-border-sm me-1"></span>
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>

    <GroupManagementModal
      v-if="showGroupModal"
      :show="showGroupModal"
      @close="showGroupModal = false"
      @groups-updated="handleGroupsUpdated"
    />
  </AdminLayout>
</template>

<style scoped>
.avatar {
  width: 32px;
  height: 32px;
  font-size: 0.75rem;
}
</style>
