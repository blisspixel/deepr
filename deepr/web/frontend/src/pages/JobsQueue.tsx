import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import Card, { CardBody } from '@/components/common/Card'
import Button from '@/components/common/Button'

export default function JobsQueue() {
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const { data: jobsData, isLoading } = useQuery({
    queryKey: ['jobs', 'list'],
    queryFn: () => jobsApi.list({}),
    refetchInterval: 5000,
  })

  const jobs = jobsData?.jobs || []

  const filteredJobs = statusFilter === 'all'
    ? jobs
    : jobs.filter(j => j.status === statusFilter)

  const getStatusText = (status: string) => {
    const map: Record<string, string> = {
      'pending': 'Queued',
      'in_progress': 'Running',
      'processing': 'Running',
      'completed': 'Done',
      'failed': 'Failed'
    }
    return map[status] || status
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Queue
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            {filteredJobs.length} job{filteredJobs.length !== 1 ? 's' : ''}
          </p>
        </div>

        <div className="flex gap-2">
          {['all', 'processing', 'completed'].map((filter) => (
            <button
              key={filter}
              onClick={() => setStatusFilter(filter)}
              className="px-3 py-1.5 text-xs rounded-lg transition-all"
              style={{
                backgroundColor: statusFilter === filter ? 'var(--color-surface)' : 'transparent',
                color: statusFilter === filter ? 'var(--color-text-primary)' : 'var(--color-text-secondary)'
              }}
            >
              {filter === 'all' ? 'All' : filter === 'processing' ? 'Active' : 'Done'}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Card>
          <CardBody>
            <p className="text-center py-8" style={{ color: 'var(--color-text-secondary)' }}>
              Loading...
            </p>
          </CardBody>
        </Card>
      ) : filteredJobs.length === 0 ? (
        <Card>
          <CardBody>
            <p className="text-center py-8" style={{ color: 'var(--color-text-secondary)' }}>
              No jobs found
            </p>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-2">
          {filteredJobs.map((job) => (
            <Card key={job.id}>
              <CardBody>
                <div className="space-y-2">
                  <div className="flex justify-between items-start gap-4">
                    <p className="text-sm flex-1" style={{ color: 'var(--color-text-primary)' }}>
                      {job.prompt.substring(0, 150)}
                      {job.prompt.length > 150 ? '...' : ''}
                    </p>
                    <span className="text-xs whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                      {getStatusText(job.status)}
                    </span>
                  </div>

                  <div className="flex justify-between items-center text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    <span>{job.model}</span>
                    {job.cost > 0 && <span>${job.cost.toFixed(2)}</span>}
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
