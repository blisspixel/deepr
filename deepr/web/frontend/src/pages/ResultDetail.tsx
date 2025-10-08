import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { resultsApi } from '@/api/results'
import ReactMarkdown from 'react-markdown'
import Card, { CardHeader, CardBody } from '@/components/common/Card'
import Button from '@/components/common/Button'

export default function ResultDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showRaw, setShowRaw] = useState(false)

  // Fetch result detail
  const { data: result, isLoading } = useQuery({
    queryKey: ['results', 'detail', id],
    queryFn: () => resultsApi.getById(id!),
    enabled: !!id,
  })

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: (format: 'markdown' | 'pdf' | 'json') =>
      resultsApi.export(id!, format),
    onSuccess: (blob, format) => {
      // Download the file
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `result-${id}.${format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading result...</div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <div className="text-6xl mb-4">❌</div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          Result Not Found
        </h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          The result you're looking for doesn't exist
        </p>
        <Button onClick={() => navigate('/results')}>Back to Library</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => navigate('/results')}
            className="mb-4"
          >
            ← Back to Library
          </Button>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            {result.prompt}
          </h1>
          <div className="flex items-center space-x-4 text-sm text-gray-500 dark:text-gray-400">
            <span className="font-mono">ID: {result.id.slice(0, 8)}</span>
            <span>•</span>
            <span>{result.model}</span>
            <span>•</span>
            <span>${result.cost.toFixed(2)}</span>
            <span>•</span>
            <span>{new Date(result.completed_at).toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Actions */}
      <Card>
        <CardBody>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Button
                size="sm"
                variant={showRaw ? 'ghost' : 'primary'}
                onClick={() => setShowRaw(false)}
              >
                Formatted
              </Button>
              <Button
                size="sm"
                variant={showRaw ? 'primary' : 'ghost'}
                onClick={() => setShowRaw(true)}
              >
                Raw Markdown
              </Button>
            </div>
            <div className="flex items-center space-x-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => exportMutation.mutate('markdown')}
                isLoading={exportMutation.isPending}
              >
                Export MD
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => exportMutation.mutate('pdf')}
                isLoading={exportMutation.isPending}
              >
                Export PDF
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => exportMutation.mutate('json')}
                isLoading={exportMutation.isPending}
              >
                Export JSON
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Content */}
      <Card>
        <CardBody>
          {showRaw ? (
            <pre className="whitespace-pre-wrap font-mono text-sm text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900 p-4 rounded-md overflow-x-auto">
              {result.content}
            </pre>
          ) : (
            <div className="prose dark:prose-invert max-w-none">
              <ReactMarkdown>{result.content}</ReactMarkdown>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Citations */}
      {result.citations && result.citations.length > 0 && (
        <Card>
          <CardHeader>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Citations ({result.citations.length})
            </h2>
          </CardHeader>
          <CardBody>
            <div className="space-y-4">
              {result.citations.map((citation, index) => (
                <div
                  key={index}
                  className="p-4 bg-gray-50 dark:bg-gray-900 rounded-md border border-gray-200 dark:border-gray-700"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-900 dark:text-white mb-1">
                        [{index + 1}] {citation.title}
                      </h3>
                      {citation.url && (
                        <a
                          href={citation.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-primary-600 dark:text-primary-400 hover:underline"
                        >
                          {citation.url}
                        </a>
                      )}
                      {citation.snippet && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                          {citation.snippet}
                        </p>
                      )}
                    </div>
                    {citation.url && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => window.open(citation.url, '_blank')}
                      >
                        Open
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Metadata */}
      <Card>
        <CardHeader>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Metadata</h2>
        </CardHeader>
        <CardBody>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                Job ID
              </h3>
              <p className="font-mono text-sm text-gray-900 dark:text-white">{result.id}</p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                Model
              </h3>
              <p className="text-sm text-gray-900 dark:text-white">{result.model}</p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                Cost
              </h3>
              <p className="text-sm text-gray-900 dark:text-white">
                ${result.cost.toFixed(2)}
              </p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                Completed At
              </h3>
              <p className="text-sm text-gray-900 dark:text-white">
                {new Date(result.completed_at).toLocaleString()}
              </p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                Content Length
              </h3>
              <p className="text-sm text-gray-900 dark:text-white">
                {result.content.length.toLocaleString()} characters
              </p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                Web Search
              </h3>
              <p className="text-sm text-gray-900 dark:text-white">
                {result.enable_web_search ? 'Enabled' : 'Disabled'}
              </p>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
