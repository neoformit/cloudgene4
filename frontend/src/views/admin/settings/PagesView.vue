<script setup>
import { ref, onMounted } from 'vue'
import { listPages, getPage, savePage, deletePage } from '@/api/admin'
import { apiErrorMessage, apiFieldErrors } from '@/api/client'
import { useServerStore } from '@/stores/server'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import AlertMessage from '@/components/common/AlertMessage.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const server = useServerStore()
const pages = ref([])
const loading = ref(true)
const current = ref(null) // {slug, html, deletable, isNew}
const preview = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const slugError = ref('')
const newSlug = ref('')
const confirmDelete = ref(false)

async function loadList() {
  try {
    pages.value = (await listPages()).data
  } catch (err) {
    error.value = apiErrorMessage(err, 'Could not load pages.')
  } finally {
    loading.value = false
  }
}

onMounted(loadList)

async function open(slug) {
  error.value = ''
  success.value = ''
  preview.value = false
  try {
    const { data } = await getPage(slug)
    current.value = { ...data, isNew: false }
  } catch (err) {
    error.value = apiErrorMessage(err)
  }
}

function startNew() {
  error.value = ''
  success.value = ''
  slugError.value = ''
  const slug = newSlug.value.trim().toLowerCase()
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(slug)) {
    slugError.value = 'Use lower-case letters, digits, "-" and "_" (max 64).'
    return
  }
  if (pages.value.some((p) => p.slug === slug)) {
    open(slug)
  } else {
    current.value = { slug, html: `<h2>${slug}</h2>\n<p></p>\n`, deletable: true, isNew: true }
  }
  newSlug.value = ''
}

async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const { data } = await savePage(current.value.slug, current.value.html)
    current.value = { ...data, isNew: false }
    success.value = `Page "${data.slug}" saved.`
    if (['footer'].includes(data.slug)) server.load(true)
    await loadList()
  } catch (err) {
    error.value = apiErrorMessage(err, 'Save failed.')
    slugError.value = apiFieldErrors(err).slug?.[0] || ''
  } finally {
    saving.value = false
  }
}

async function doDelete() {
  confirmDelete.value = false
  try {
    await deletePage(current.value.slug)
    success.value = `Page "${current.value.slug}" deleted.`
    current.value = null
    await loadList()
  } catch (err) {
    error.value = apiErrorMessage(err)
  }
}

const publicUrl = (slug) => (slug === 'home' ? '/' : slug === 'footer' ? null : `/pages/${slug}`)
</script>

<template>
  <AdminLayout>
    <h2 class="mb-1">Pages</h2>
    <p class="text-muted small">
      HTML files in <code>$CLOUDGENE_HOME/pages/</code>: <code>home</code> is the welcome page,
      <code>footer</code> the site footer, any other page is served at <code>/pages/&lt;name&gt;</code>
      (link it from the navigation in General settings).
    </p>

    <AlertMessage :message="error" />
    <div v-if="success" class="alert alert-success" data-testid="pages-success">{{ success }}</div>
    <LoadingSpinner v-if="loading" />

    <div v-else class="row g-3">
      <div class="col-md-3">
        <div class="list-group mb-3" data-testid="pages-list">
          <button
            v-for="p in pages"
            :key="p.slug"
            type="button"
            class="list-group-item list-group-item-action d-flex justify-content-between"
            :class="{ active: current?.slug === p.slug }"
            data-testid="page-item"
            :data-slug="p.slug"
            @click="open(p.slug)"
          >
            <span>{{ p.slug }}</span>
            <small v-if="!p.deletable" class="opacity-75">required</small>
          </button>
        </div>
        <form class="input-group input-group-sm" data-testid="page-new-form" @submit.prevent="startNew">
          <input v-model="newSlug" class="form-control" :class="{ 'is-invalid': slugError }" placeholder="new-page" data-testid="page-new-slug" />
          <button class="btn btn-outline-primary" type="submit" data-testid="page-new">New page</button>
          <div class="invalid-feedback">{{ slugError }}</div>
        </form>
      </div>

      <div class="col-md-9">
        <div v-if="!current" class="text-muted">Select a page to edit.</div>
        <form v-else data-testid="page-editor" @submit.prevent="save">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <h5 class="mb-0">
              <code data-testid="page-editor-slug">{{ current.slug }}</code>
              <span v-if="current.isNew" class="badge bg-info ms-2">new</span>
            </h5>
            <div class="btn-group btn-group-sm">
              <button type="button" class="btn" :class="preview ? 'btn-outline-secondary' : 'btn-secondary'" data-testid="page-tab-edit" @click="preview = false">Edit</button>
              <button type="button" class="btn" :class="preview ? 'btn-secondary' : 'btn-outline-secondary'" data-testid="page-tab-preview" @click="preview = true">Preview</button>
            </div>
          </div>
          <textarea
            v-if="!preview"
            v-model="current.html"
            class="form-control font-monospace"
            rows="18"
            spellcheck="false"
            data-testid="page-html"
          ></textarea>
          <!-- preview of admin-authored HTML -->
          <div v-else class="border rounded p-3" data-testid="page-preview" v-html="current.html"></div>
          <div class="d-flex gap-2 mt-2">
            <button class="btn btn-primary" type="submit" data-testid="page-save" :disabled="saving">
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>Save
            </button>
            <a
              v-if="!current.isNew && publicUrl(current.slug)"
              :href="publicUrl(current.slug)"
              target="_blank"
              class="btn btn-outline-secondary"
              data-testid="page-view"
            >View</a>
            <button
              v-if="current.deletable && !current.isNew"
              type="button"
              class="btn btn-outline-danger ms-auto"
              data-testid="page-delete"
              @click="confirmDelete = true"
            >Delete</button>
          </div>
        </form>
      </div>
    </div>

    <ConfirmDialog
      v-if="confirmDelete"
      title="Delete page"
      message="Delete this page file? This cannot be undone."
      confirm-text="Delete"
      @confirm="doDelete"
      @cancel="confirmDelete = false"
    />
  </AdminLayout>
</template>
