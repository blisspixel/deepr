import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { plannerApi } from '@/api/planner'
import Card, { CardHeader, CardBody } from '@/components/common/Card'
import Button from '@/components/common/Button'

export default function BatchStatus() {
  const { batchId } = useParams<{ batchId: string }>()
  const navigate = useNavigate()

  // Fetch batch status with polling
  const { data: batch, isLoading } = useQuery({
    queryKey: ['batch', 'status', batchId],
    queryFn: () => plannerApi.getBatchStatus(batchId!),
    enabled: !!batchId,
    refetchInterval: 5000, // Poll every 5 seconds
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading batch status...</div>
      </div>
    )
  }

  if (!batch) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <div className="text-6xl mb-4">❌</div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          Batch Not Found
        </h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          The batch you're looking for doesn't exist
        </p>
        <Button onClick={() => navigate('/prep')}>Back to Prep</Button>
      </div>
    )
  }

  const getStatusBadge = (status: string) => {
    const badges = {
      completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
      in_progress: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
      failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
      pending: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
    }
    return badges[status as keyof typeof badges] || badges.pending
  }

  const progressPercentage =
    batch.summary.total > 0
      ? ((batch.summary.completed + batch.summary.failed) / batch.summary.total) * 100
      : 0

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <Button size="sm" variant="ghost" onClick={() => navigate('/prep')} className="mb-4">
          ← Back to Prep
        </Button>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Batch: {batch.scenario}
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1 font-mono text-sm">
          ID: {batch.batch_id}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card>
          <CardBody>
            <p className="text-sm text-gray-600 dark:text-gray-400">Total</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {batch.summary.total}
            </p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="text-sm text-gray-600 dark:text-gray-400">Completed</p>
            <p className="text-2xl font-bold text-green-600">{batch.summary.completed}</p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="text-sm text-gray-600 dark:text-gray-400">In Progress</p>
            <p className="text-2xl font-bold text-blue-600">{batch.summary.in_progress}</p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="text-sm text-gray-600 dark:text-gray-400">Pending</p>
            <p className="text-2xl font-bold text-gray-600">{batch.summary.pending}</p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="text-sm text-gray-600 dark:text-gray-400">Failed</p>
            <p className="text-2xl font-bold text-red-600">{batch.summary.failed}</p>
          </CardBody>
        </Card>
      </div>

      {/* Progress Bar */}
      <Card>
        <CardBody>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">Overall Progress</span>
              <span className="font-semibold text-gray-900 dark:text-white">
                {progressPercentage.toFixed(0)}%
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
              <div
                className="bg-primary-600 h-4 rounded-full transition-all duration-500"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>
                {batch.summary.completed + batch.summary.failed} / {batch.summary.total} tasks
                complete
              </span>
              <span>${batch.summary.total_cost.toFixed(2)} spent</span>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Jobs List */}
      <Card>
        <CardHeader>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Research Tasks</h2>
        </CardHeader>
        <CardBody>
          <div className="space-y-3">
            {batch.jobs.map((job) => (
              <div
                key={job.id}
                className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-1">
                      <h3 className="font-semibold text-gray-900 dark:text-white">
                        {job.title}
                      </h3>
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(
                          job.status
                        )}`}
                      >
                        {job.status}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{job.prompt}</p>
                    <div className="flex items-center space-x-4 text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-mono">{job.id.slice(0, 8)}</span>
                      <span>
                        {job.actual_cost
                          ? `$${job.actual_cost.toFixed(2)}`
                          : job.estimated_cost
                          ? `~$${job.estimated_cost.toFixed(2)}`
                          : '-'}
                      </span>
                      {job.created_at && (
                        <span>{new Date(job.created_at).toLocaleString()}</span>
                      )}
                    </div>
                  </div>
                  {job.status === 'completed' && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => navigate(`/results/${job.id}`)}
                    >
                      View Result
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Actions */}
      {batch.summary.completed > 0 && (
        <Card className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
          <CardBody>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-green-900 dark:text-green-300 mb-1">
                  ✓ {batch.summary.completed} Research {batch.summary.completed === 1 ? 'Task' : 'Tasks'} Complete
                </h3>
                <p className="text-sm text-green-800 dark:text-green-400">
                  View your research results in the Results Library
                </p>
              </div>
              <Button variant="secondary" onClick={() => navigate('/results')}>
                View All Results
              </Button>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
