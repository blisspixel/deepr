import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import Card, { CardHeader, CardBody } from '@/components/common/Card'
import Button from '@/components/common/Button'
import TextArea from '@/components/common/TextArea'
import Select from '@/components/common/Select'

export default function Dashboard() {
  const navigate = useNavigate()
  const [quickPrompt, setQuickPrompt] = useState('')
  const [quickModel, setQuickModel] = useState('o4-mini-deep-research')

  // Fetch recent jobs
  const { data: jobsData } = useQuery({
    queryKey: ['jobs', 'recent'],
    queryFn: () => jobsApi.list({ limit: 5 }),
    refetchInterval: 5000,
  })

  // Fetch cost summary
  const { data: costSummary } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 10000,
  })

  // Estimate cost for quick prompt
  const { data: costEstimate, isLoading: isEstimating } = useQuery({
    queryKey: ['cost', 'estimate', quickPrompt, quickModel],
    queryFn: () =>
      costApi.estimate({
        prompt: quickPrompt,
        model: quickModel,
        enable_web_search: true,
      }),
    enabled: quickPrompt.length > 10,
  })

  const handleQuickSubmit = async () => {
    if (!quickPrompt.trim()) return

    try {
      await jobsApi.submit({
        prompt: quickPrompt,
        model: quickModel,
        priority: 1,
        enable_web_search: true,
      })
      setQuickPrompt('')
      navigate('/jobs')
    } catch (error) {
      console.error('Failed to submit job:', error)
    }
  }

  const recentJobs = jobsData?.jobs || []

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          Dashboard
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          Quick access to research automation
        </p>
      </div>

      {/* Quick Submit Form */}
      <Card>
        <CardBody>
          <div className="space-y-4">
            <TextArea
              label="Research Prompt"
              placeholder="What would you like to research?"
              value={quickPrompt}
              onChange={(e) => setQuickPrompt(e.target.value)}
              rows={4}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Select
                label="Model"
                value={quickModel}
                onChange={(e) => setQuickModel(e.target.value)}
                options={[
                  { value: 'o4-mini-deep-research', label: 'o4-mini (Faster, Cheaper)' },
                  { value: 'o3-deep-research', label: 'o3 (More Thorough)' },
                ]}
              />

              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-primary)' }}>
                  Estimated Cost
                </label>
                <div className="px-3 py-2 border rounded-lg" style={{ borderColor: 'var(--color-border)' }}>
                  {isEstimating ? (
                    <span style={{ color: 'var(--color-text-secondary)' }}>Calculating...</span>
                  ) : costEstimate ? (
                    <div>
                      <span className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                        ${costEstimate.estimate.expected_cost.toFixed(2)}
                      </span>
                      <span className="text-sm ml-2" style={{ color: 'var(--color-text-secondary)' }}>
                        (${costEstimate.estimate.min_cost.toFixed(2)} - $
                        {costEstimate.estimate.max_cost.toFixed(2)})
                      </span>
                    </div>
                  ) : (
                    <span style={{ color: 'var(--color-text-secondary)' }}>Type a prompt to estimate</span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => navigate('/submit')}>
                Advanced Options
              </Button>
              <Button onClick={handleQuickSubmit} disabled={!quickPrompt.trim()}>
                Submit Research
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div
          className="p-5 border rounded-xl"
          style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}
        >
          <p className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide">
            Active Jobs
          </p>
          <p className="text-3xl font-semibold mt-2 text-[var(--color-text-primary)] tabular-nums">
            {recentJobs.filter((j) => ['queued', 'processing'].includes(j.status)).length}
          </p>
        </div>

        <div
          className="p-5 border rounded-xl"
          style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}
        >
          <p className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide">
            Today's Spending
          </p>
          <p className="text-3xl font-semibold mt-2 text-[var(--color-text-primary)] tabular-nums">
            ${costSummary?.daily.toFixed(2) || '0.00'}
          </p>
          <p className="text-xs mt-1.5 text-[var(--color-text-tertiary)]">
            of ${costSummary?.daily_limit.toFixed(2) || '100.00'} limit
          </p>
        </div>

        <div
          className="p-5 border rounded-xl"
          style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}
        >
          <p className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide">
            Monthly Spending
          </p>
          <p className="text-3xl font-semibold mt-2 text-[var(--color-text-primary)] tabular-nums">
            ${costSummary?.monthly.toFixed(2) || '0.00'}
          </p>
          <p className="text-xs mt-1.5 text-[var(--color-text-tertiary)]">
            of ${costSummary?.monthly_limit.toFixed(2) || '1000.00'} limit
          </p>
        </div>
      </div>

      {/* Recent Jobs */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Recent Jobs
          </h2>
          <Button variant="ghost" size="sm" onClick={() => navigate('/jobs')}>
            View All
          </Button>
        </div>

        {recentJobs.length === 0 ? (
          <div
            className="text-center py-12 border rounded-xl"
            style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}
          >
            <p className="text-[var(--color-text-secondary)]">
              No jobs yet. Submit your first research task above.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {recentJobs.map((job) => (
              <div
                key={job.id}
                className="p-4 border rounded-xl cursor-pointer transition-all duration-150 hover:border-[var(--color-border-hover)] hover:shadow-sm"
                style={{
                  borderColor: 'var(--color-border)',
                  backgroundColor: 'var(--color-surface)'
                }}
                onClick={() => navigate(`/jobs`)}
              >
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate text-[var(--color-text-primary)]">
                      {job.prompt.substring(0, 100)}
                      {job.prompt.length > 100 ? '...' : ''}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-xs text-[var(--color-text-tertiary)]">{job.model}</span>
                      <span className="text-[var(--color-border)]">·</span>
                      <span className={`badge ${
                        job.status === 'completed' ? 'badge-success' :
                        job.status === 'failed' ? 'badge-error' :
                        job.status === 'processing' ? 'badge-info' : 'badge-neutral'
                      }`}>
                        {job.status}
                      </span>
                    </div>
                  </div>
                  {job.cost > 0 && (
                    <span className="text-sm font-semibold text-[var(--color-text-primary)] tabular-nums">
                      ${job.cost.toFixed(2)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
