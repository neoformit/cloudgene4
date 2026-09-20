<script setup>
import { ref, onMounted } from 'vue'
import { listUsers, updateUser } from '@/api/users'
import { apiErrorMessage } from '@/api/client'
import { avatarHue, initials } from '@/utils/avatar'
import AlertMessage from '@/components/common/AlertMessage.vue'

const props = defineProps({
  group: { type: Object, required: true },
})
const emit = defineEmits(['close', 'members-changed'])

const members = ref([])
const loading = ref(true)
const error = ref('')
const removing = ref(null)

async function refresh() {
  loading.value = true
  try {
    const { data } = await listUsers({ group: props.group.name, page_size: 200 })
    members.value = data.results
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load members.')
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function remove(user) {
  removing.value = user.id
  error.value = ''
  try {
    if (props.group.name === 'admin') {
      await updateUser(user.id, { is_admin: false })
    } else {
      await updateUser(user.id, { groups: user.groups.filter((g) => g !== props.group.name && g !== 'admin') })
    }
    await refresh()
    emit('members-changed')
  } catch (e) {
    error.value = apiErrorMessage(e, 'Removing the member failed.')
  } finally {
    removing.value = null
  }
}
</script>

<template>
  <div
    class="modal d-block"
    tabindex="-1"
    style="background: rgba(0,0,0,0.5); z-index: 1060;"
    data-testid="group-members-modal"
    @click.self="emit('close')"
  >
    <div class="modal-dialog modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Members of <strong>{{ group.name }}</strong></h5>
          <button type="button" class="btn-close" aria-label="Close" @click="emit('close')"></button>
        </div>
        <div class="modal-body">
          <AlertMessage :message="error" data-testid="group-members-error" />
          <div v-if="loading" class="text-muted">Loading…</div>
          <ul v-else-if="members.length" class="list-group">
            <li
              v-for="user in members"
              :key="user.id"
              class="list-group-item d-flex align-items-center gap-2"
              data-testid="group-member"
              :data-username="user.username"
            >
              <span
                class="avatar rounded-circle d-inline-flex align-items-center justify-content-center text-white fw-bold"
                :style="{ background: `hsl(${avatarHue(user)}, 45%, 45%)` }"
                aria-hidden="true"
              >{{ initials(user) }}</span>
              <div class="flex-grow-1">
                <div class="fw-semibold">{{ user.username }}</div>
                <small class="text-muted">{{ user.full_name }}</small>
              </div>
              <button
                class="btn btn-sm btn-outline-danger"
                :disabled="removing === user.id || user.is_superuser"
                data-testid="group-member-remove"
                @click="remove(user)"
              >
                Remove
              </button>
            </li>
          </ul>
          <p v-else class="text-muted mb-0" data-testid="group-members-empty">
            No members. Add users to this group from the user list.
          </p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-testid="group-members-close" @click="emit('close')">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.avatar {
  width: 24px;
  height: 24px;
  font-size: 0.6rem;
}
</style>
