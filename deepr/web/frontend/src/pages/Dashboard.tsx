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
        <div className="p-4 border rounded-lg" style={{ borderColor: 'var(--color-border)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            Active Jobs
          </p>
          <p className="text-3xl font-semibold mt-1" style={{ color: 'var(--color-text-primary)' }}>
            {recentJobs.filter((j) => ['pending', 'in_progress'].includes(j.status)).length}
          </p>
        </div>

        <div className="p-4 border rounded-lg" style={{ borderColor: 'var(--color-border)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            Today's Spending
          </p>
          <p className="text-3xl font-semibold mt-1" style={{ color: 'var(--color-text-primary)' }}>
            ${costSummary?.daily.toFixed(2) || '0.00'}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            of ${costSummary?.daily_limit.toFixed(2) || '100.00'} limit
          </p>
        </div>

        <div className="p-4 border rounded-lg" style={{ borderColor: 'var(--color-border)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            Monthly Spending
          </p>
          <p className="text-3xl font-semibold mt-1" style={{ color: 'var(--color-text-primary)' }}>
            ${costSummary?.monthly.toFixed(2) || '0.00'}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
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
          <div className="text-center py-12 border rounded-lg" style={{ borderColor: 'var(--color-border)' }}>
            <p style={{ color: 'var(--color-text-secondary)' }}>
              No jobs yet. Submit your first research task above!
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {recentJobs.map((job) => (
              <div
                key={job.id}
                className="p-4 border rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                style={{ borderColor: 'var(--color-border)' }}
                onClick={() => navigate(`/jobs`)}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate" style={{ color: 'var(--color-text-primary)' }}>
                      {job.prompt.substring(0, 100)}
                      {job.prompt.length > 100 ? '...' : ''}
                    </p>
                    <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                      {job.model} · {job.status}
                    </p>
                  </div>
                  {job.cost > 0 && (
                    <span className="text-sm font-medium ml-4" style={{ color: 'var(--color-text-primary)' }}>
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
