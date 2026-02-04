import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import Button from '@/components/common/Button'

export default function JobsQueue() {
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const queryClient = useQueryClient()

  const { data: jobsData, isLoading } = useQuery({
    queryKey: ['jobs', 'list'],
    queryFn: () => jobsApi.list({}),
    refetchInterval: 5000,
  })

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => jobsApi.cancel(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const jobs = jobsData?.jobs || []

  const filteredJobs = statusFilter === 'all'
    ? jobs
    : jobs.filter(j => {
        if (statusFilter === 'active') return ['queued', 'processing'].includes(j.status)
        return j.status === statusFilter
      })

  const getStatusBadge = (status: string) => {
    const config: Record<string, { class: string; label: string }> = {
      'queued': { class: 'badge-neutral', label: 'Queued' },
      'processing': { class: 'badge-info', label: 'Running' },
      'completed': { class: 'badge-success', label: 'Done' },
      'failed': { class: 'badge-error', label: 'Failed' },
      'cancelled': { class: 'badge-warning', label: 'Cancelled' },
    }
    return config[status] || { class: 'badge-neutral', label: status }
  }

  const filters = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'completed', label: 'Done' },
    { key: 'failed', label: 'Failed' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            Queue
          </h1>
          <p className="text-sm mt-1 text-[var(--color-text-secondary)]">
            {filteredJobs.length} job{filteredJobs.length !== 1 ? 's' : ''}
          </p>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-1 p-1 rounded-lg bg-[var(--color-surface)]">
          {filters.map((filter) => (
            <button
              key={filter.key}
              onClick={() => setStatusFilter(filter.key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-150 ${
                statusFilter === filter.key
                  ? 'bg-[var(--color-bg)] text-[var(--color-text-primary)] shadow-sm'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {/* Jobs List */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="p-4 border rounded-xl bg-[var(--color-surface)]"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <div className="skeleton h-4 w-3/4 mb-3" />
              <div className="skeleton h-3 w-1/4" />
            </div>
          ))}
        </div>
      ) : filteredJobs.length === 0 ? (
        <div
          className="text-center py-12 border rounded-xl bg-[var(--color-surface)]"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <p className="text-[var(--color-text-secondary)]">
            No jobs found
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredJobs.map((job) => {
            const statusBadge = getStatusBadge(job.status)
            const isActive = ['queued', 'processing'].includes(job.status)

            return (
              <div
                key={job.id}
                className="p-4 border rounded-xl transition-all duration-150 hover:border-[var(--color-border-hover)]"
                style={{
                  borderColor: 'var(--color-border)',
                  backgroundColor: 'var(--color-surface)'
                }}
              >
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[var(--color-text-primary)] line-clamp-2">
                      {job.prompt}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs text-[var(--color-text-tertiary)]">
                        {job.model}
                      </span>
                      <span className="text-[var(--color-border)]">·</span>
                      <span className={`badge ${statusBadge.class}`}>
                        {statusBadge.label}
                      </span>
                      {job.cost > 0 && (
                        <>
                          <span className="text-[var(--color-border)]">·</span>
                          <span className="text-xs font-medium text-[var(--color-text-secondary)] tabular-nums">
                            ${job.cost.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {isActive && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => cancelMutation.mutate(job.id)}
                      disabled={cancelMutation.isPending}
                    >
                      Cancel
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
