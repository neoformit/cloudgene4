import { defineStore } from 'pinia'
import { listJobs, getJob } from '@/api/jobs'

export const useJobsStore = defineStore('jobs', {
  state: () => ({
    jobs: [],
    total: 0,
    currentPage: 1,
    stateFilter: '',
  }),

  actions: {
    async fetchJobs(page = 1, stateFilter = this.stateFilter) {
      const params = { page }
      if (stateFilter) params.state = stateFilter
      const { data } = await listJobs(params)
      this.jobs = data.results ?? data
      this.total = data.count ?? this.jobs.length
      this.currentPage = page
      this.stateFilter = stateFilter
      return this.jobs
    },

    async refreshJob(id) {
      const { data } = await getJob(id)
      const idx = this.jobs.findIndex((j) => j.id === id)
      if (idx !== -1) this.jobs[idx] = data
      return data
    },
  },
})
