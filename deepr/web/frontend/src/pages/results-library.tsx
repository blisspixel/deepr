import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { resultsApi } from '@/api/results'
import { cn, formatCurrency, formatRelativeTime, truncateText } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  FileText,
  Grid3X3,
  List,
  Plus,
  Search,
} from 'lucide-react'
import { CardGridSkeleton } from '@/components/ui/skeleton'

type ViewMode = 'grid' | 'list'

export default function ResultsLibrary() {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState('date')
  const [page, setPage] = useState(0)
  const pageSize = 12

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data: resultsData, isLoading, isError, refetch } = useQuery({
    queryKey: ['results', 'list', debouncedSearch, sortBy, page],
    queryFn: () => resultsApi.list({
      search: debouncedSearch || undefined,
      sort_by: sortBy,
      limit: pageSize,
      offset: page * pageSize,
    }),
    refetchInterval: 10000,
  })

  const results = resultsData?.results || []
  const total = resultsData?.total ?? results.length
  const totalPages = Math.ceil(total / pageSize)

  if (isLoading) return <CardGridSkeleton />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <AlertTriangle className="w-10 h-10 text-destructive mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Failed to load results</p>
        <p className="text-sm text-muted-foreground mb-4">
          Could not connect to the backend. Results will appear here once the server is running.
        </p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Results</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {total} result{total !== 1 ? 's' : ''}
          </p>
        </div>
        <Button onClick={() => navigate('/research')}>
          <Plus className="w-4 h-4" />
          New Research
        </Button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search results..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Sort */}
        <Select value={sortBy} onValueChange={(v) => { setSortBy(v); setPage(0) }}>
          <SelectTrigger className="w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="date">Newest First</SelectItem>
            <SelectItem value="cost">Highest Cost</SelectItem>
            <SelectItem value="model">Model</SelectItem>
          </SelectContent>
        </Select>

        {/* View Toggle */}
        <div className="flex gap-1 p-1 bg-secondary rounded-lg">
          <button
            onClick={() => setViewMode('grid')}
            aria-label="Grid view"
            className={cn(
              'p-1.5 rounded-md transition-all',
              viewMode === 'grid' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
            )}
          >
            <Grid3X3 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            aria-label="List view"
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
      {results.length === 0 ? (
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
              className="rounded-lg border bg-card hover:border-primary/20 hover:shadow-md transition-all cursor-pointer group"
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

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Showing {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} of {total}
          </p>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const start = Math.max(0, Math.min(page - 2, totalPages - 5))
              const pageNum = start + i
              return (
                <Button
                  key={pageNum}
                  variant={pageNum === page ? 'default' : 'outline'}
                  size="icon"
                  className="h-8 w-8 text-xs"
                  onClick={() => setPage(pageNum)}
                >
                  {pageNum + 1}
                </Button>
              )
            })}
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => p + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
