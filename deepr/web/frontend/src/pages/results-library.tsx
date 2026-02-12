import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { resultsApi } from '@/api/results'
import { cn, formatCurrency, formatRelativeTime, truncateText } from '@/lib/utils'
import {
  FileText,
  Grid3X3,
  List,
  Loader2,
  Plus,
  Search,
} from 'lucide-react'

type ViewMode = 'grid' | 'list'

export default function ResultsLibrary() {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState('date')

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data: resultsData, isLoading } = useQuery({
    queryKey: ['results', 'list', debouncedSearch, sortBy],
    queryFn: () => resultsApi.list({ search: debouncedSearch || undefined, sort_by: sortBy }),
    refetchInterval: 10000,
  })

  const results = resultsData?.results || []

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Results</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {results.length} result{results.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={() => navigate('/research')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Research
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search results..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-background border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
          />
        </div>

        {/* Sort */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="px-3 py-2 bg-background border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="date">Newest First</option>
          <option value="cost">Highest Cost</option>
          <option value="model">Model</option>
        </select>

        {/* View Toggle */}
        <div className="flex gap-1 p-1 bg-secondary rounded-lg">
          <button
            onClick={() => setViewMode('grid')}
            className={cn(
              'p-1.5 rounded-md transition-all',
              viewMode === 'grid' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
            )}
          >
            <Grid3X3 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'p-1.5 rounded-md transition-all',
              viewMode === 'list' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
            )}
          >
            <List className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : results.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <FileText className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <h3 className="text-base font-medium text-foreground mb-1">No results yet</h3>
          <p className="text-sm text-muted-foreground mb-4">Complete research jobs will appear here.</p>
          <button
            onClick={() => navigate('/research')}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
          >
            Submit Research
          </button>
        </div>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {results.map((result) => (
            <div
              key={result.id}
              className="rounded-lg border bg-card hover:border-primary/20 transition-all cursor-pointer group"
              onClick={() => navigate(`/results/${result.id}`)}
            >
              <div className="p-4 space-y-3">
                <p className="text-sm font-medium text-foreground line-clamp-2 group-hover:text-primary transition-colors">
                  {result.prompt}
                </p>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {truncateText(result.content, 150)}
                </p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
                  <span className="px-1.5 py-0.5 bg-secondary rounded text-[10px] font-medium">{result.model}</span>
                  <span>{formatCurrency(result.cost)}</span>
                  {result.citations_count > 0 && (
                    <span>{result.citations_count} citations</span>
                  )}
                  <span className="ml-auto">{formatRelativeTime(result.completed_at)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border bg-card divide-y">
          {results.map((result) => (
            <div
              key={result.id}
              className="p-4 flex items-start gap-4 cursor-pointer hover:bg-accent/50 transition-colors"
              onClick={() => navigate(`/results/${result.id}`)}
            >
              <div className="flex-1 min-w-0 space-y-1">
                <p className="text-sm font-medium text-foreground">{result.prompt}</p>
                <p className="text-xs text-muted-foreground line-clamp-1">
                  {truncateText(result.content, 200)}
                </p>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="px-1.5 py-0.5 bg-secondary rounded text-[10px] font-medium">{result.model}</span>
                  <span>{formatCurrency(result.cost)}</span>
                  {result.citations_count > 0 && <span>{result.citations_count} citations</span>}
                  <span>{formatRelativeTime(result.completed_at)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Stats Footer */}
      {results.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Total Results', value: results.length.toString() },
            { label: 'Total Cost', value: formatCurrency(results.reduce((sum, r) => sum + r.cost, 0)) },
            { label: 'Total Citations', value: results.reduce((sum, r) => sum + (r.citations_count || 0), 0).toString() },
            { label: 'Avg Length', value: `${Math.round(results.reduce((sum, r) => sum + (r.content?.length || 0), 0) / results.length / 1000)}k chars` },
          ].map((stat) => (
            <div key={stat.label} className="rounded-lg border bg-card p-3 text-center">
              <p className="text-lg font-semibold text-foreground tabular-nums">{stat.value}</p>
              <p className="text-xs text-muted-foreground">{stat.label}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
