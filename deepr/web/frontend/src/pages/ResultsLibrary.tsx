import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { resultsApi } from '@/api/results'
import Card, { CardHeader, CardBody } from '@/components/common/Card'
import Button from '@/components/common/Button'
import Input from '@/components/common/Input'
import Select from '@/components/common/Select'

type ViewMode = 'grid' | 'list'

export default function ResultsLibrary() {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState('date')

  // Fetch results
  const { data: resultsData, isLoading } = useQuery({
    queryKey: ['results', 'list', searchQuery, sortBy],
    queryFn: () =>
      resultsApi.list({
        search: searchQuery || undefined,
        sort_by: sortBy,
      }),
    refetchInterval: 10000,
  })

  const results = resultsData?.results || []

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const truncateText = (text: string, maxLength: number) => {
    if (text.length <= maxLength) return text
    return text.slice(0, maxLength) + '...'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Results Library</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {results.length} result{results.length !== 1 ? 's' : ''} available
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button
            size="sm"
            variant={viewMode === 'grid' ? 'primary' : 'ghost'}
            onClick={() => setViewMode('grid')}
          >
            Grid
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'list' ? 'primary' : 'ghost'}
            onClick={() => setViewMode('list')}
          >
            List
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardBody>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              placeholder="Search results by prompt or content..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <Select
              label="Sort By"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              options={[
                { value: 'date', label: 'Date (Newest First)' },
                { value: 'cost', label: 'Cost (Highest First)' },
                { value: 'model', label: 'Model' },
              ]}
            />
          </div>
        </CardBody>
      </Card>

      {/* Results Grid/List */}
      {isLoading ? (
        <Card>
          <CardBody>
            <div className="text-center py-8 text-gray-500">Loading results...</div>
          </CardBody>
        </Card>
      ) : results.length === 0 ? (
        <Card>
          <CardBody>
            <div className="text-center py-12">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                No results yet
              </h3>
              <p className="text-gray-600 dark:text-gray-400 mb-4">
                Complete research jobs will appear here
              </p>
              <Button onClick={() => navigate('/submit')}>Submit Your First Research</Button>
            </div>
          </CardBody>
        </Card>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {results.map((result) => (
            <Card
              key={result.id}
              className="hover:shadow-lg transition-shadow cursor-pointer"
              onClick={() => navigate(`/results/${result.id}`)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white line-clamp-2">
                    {result.prompt}
                  </h3>
                </div>
              </CardHeader>
              <CardBody className="space-y-3">
                {/* Preview */}
                <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-3">
                  {truncateText(result.content, 150)}
                </p>

                {/* Metadata */}
                <div className="space-y-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 dark:text-gray-400">Model</span>
                    <span className="text-gray-900 dark:text-white font-medium">
                      {result.model}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 dark:text-gray-400">Cost</span>
                    <span className="text-gray-900 dark:text-white font-medium">
                      ${result.cost.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 dark:text-gray-400">Completed</span>
                    <span className="text-gray-900 dark:text-white font-medium">
                      {formatDate(result.completed_at)}
                    </span>
                  </div>
                  {result.citations_count > 0 && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-500 dark:text-gray-400">Citations</span>
                      <span className="text-gray-900 dark:text-white font-medium">
                        {result.citations_count}
                      </span>
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {results.map((result) => (
            <Card
              key={result.id}
              className="hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => navigate(`/results/${result.id}`)}
            >
              <CardBody>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0 space-y-2">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {result.prompt}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                      {truncateText(result.content, 250)}
                    </p>
                    <div className="flex items-center space-x-4 text-xs text-gray-500 dark:text-gray-400">
                      <span>{result.model}</span>
                      <span>${result.cost.toFixed(2)}</span>
                      <span>{formatDate(result.completed_at)}</span>
                      {result.citations_count > 0 && (
                        <span>{result.citations_count} citations</span>
                      )}
                    </div>
                  </div>
                  <div className="ml-4">
                    <Button size="sm" variant="ghost">
                      View
                    </Button>
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {/* Stats Footer */}
      {results.length > 0 && (
        <Card className="bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
          <CardBody>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold text-blue-900 dark:text-blue-300">
                  {results.length}
                </p>
                <p className="text-sm text-blue-700 dark:text-blue-400">Total Results</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-900 dark:text-blue-300">
                  ${results.reduce((sum, r) => sum + r.cost, 0).toFixed(2)}
                </p>
                <p className="text-sm text-blue-700 dark:text-blue-400">Total Cost</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-900 dark:text-blue-300">
                  {results.reduce((sum, r) => sum + (r.citations_count || 0), 0)}
                </p>
                <p className="text-sm text-blue-700 dark:text-blue-400">Total Citations</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-900 dark:text-blue-300">
                  {Math.round(
                    results.reduce((sum, r) => sum + r.content.length, 0) / results.length / 1000
                  )}
                  k
                </p>
                <p className="text-sm text-blue-700 dark:text-blue-400">Avg. Content Length</p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
