import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { resultsApi } from '@/api/results'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn, formatCurrency } from '@/lib/utils'
import { toast } from 'sonner'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  ChevronDown,
  Clock,
  Code2,
  DollarSign,
  Download,
  ExternalLink,
  FileText,
  Hash,
  Loader2,
  Search,
} from 'lucide-react'

export default function ResultDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [showRaw, setShowRaw] = useState(false)
  const [showExport, setShowExport] = useState(false)
  const [showMobileCitations, setShowMobileCitations] = useState(false)
  const [activeCitation, setActiveCitation] = useState<number | null>(null)
  const exportRef = useRef<HTMLDivElement>(null)

  // Close export dropdown on click outside
  useEffect(() => {
    if (!showExport) return
    const handler = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setShowExport(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showExport])

  const { data: result, isLoading, isError, refetch } = useQuery({
    queryKey: ['results', 'detail', id],
    queryFn: () => resultsApi.getById(id!),
    enabled: !!id,
  })

  const exportMutation = useMutation({
    mutationFn: (format: 'markdown' | 'pdf' | 'json') => resultsApi.export(id!, format),
    onSuccess: (blob, format) => {
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `result-${id}.${format === 'markdown' ? 'md' : format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      setShowExport(false)
      toast.success(`Exported as ${format.toUpperCase()}`)
    },
    onError: () => {
      toast.error('Export failed')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <AlertTriangle className="w-10 h-10 text-destructive mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Failed to load result</p>
        <p className="text-sm text-muted-foreground mb-4">Something went wrong fetching this result.</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <FileText className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Result not found</p>
        <p className="text-sm text-muted-foreground mb-4">This result doesn't exist or was deleted.</p>
        <button onClick={() => navigate('/results')} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
          Back to Results
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-7rem)]">
      {/* Main content */}
      <div className="flex-1 overflow-auto p-6 space-y-6">
        {/* Header */}
        <div className="space-y-3">
          <button
            onClick={() => navigate('/results')}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Results
          </button>

          <h1 className="text-xl font-semibold text-foreground">{result.prompt}</h1>

          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span className="px-2 py-0.5 bg-secondary rounded text-xs font-medium">{result.model}</span>
            <span className="inline-flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5" />
              {formatCurrency(result.cost)}
            </span>
            <span className="inline-flex items-center gap-1">
              <BookOpen className="w-3.5 h-3.5" />
              {result.citations_count} citations
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {new Date(result.completed_at).toLocaleDateString()}
            </span>
          </div>
        </div>

        {/* View toggle + Actions */}
        <div className="flex items-center justify-between">
          <div className="flex gap-1 p-1 bg-secondary rounded-lg">
            <button
              onClick={() => setShowRaw(false)}
              className={cn(
                'px-3 py-1 rounded-md text-xs font-medium transition-all inline-flex items-center gap-1.5',
                !showRaw ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
              )}
            >
              <BookOpen className="w-3.5 h-3.5" />
              Formatted
            </button>
            <button
              onClick={() => setShowRaw(true)}
              className={cn(
                'px-3 py-1 rounded-md text-xs font-medium transition-all inline-flex items-center gap-1.5',
                showRaw ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
              )}
            >
              <Code2 className="w-3.5 h-3.5" />
              Raw
            </button>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative" ref={exportRef}>
              <button
                onClick={() => setShowExport(!showExport)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-medium text-foreground hover:bg-accent transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Export
                <ChevronDown className="w-3 h-3" />
              </button>
              {showExport && (
                <div className="absolute right-0 mt-1 w-40 bg-popover border rounded-lg shadow-lg z-10 py-1">
                  {(['markdown', 'pdf', 'json'] as const).map((format) => (
                    <button
                      key={format}
                      onClick={() => exportMutation.mutate(format)}
                      disabled={exportMutation.isPending}
                      className="w-full px-3 py-1.5 text-left text-sm hover:bg-accent transition-colors"
                    >
                      {format.toUpperCase()}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={() => navigate(`/traces/${id}`)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-medium text-foreground hover:bg-accent transition-colors"
            >
              <Search className="w-3.5 h-3.5" />
              Trace
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="rounded-lg border bg-card p-6">
          {showRaw ? (
            <pre className="whitespace-pre-wrap font-mono text-sm text-foreground overflow-x-auto">
              {result.content}
            </pre>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-foreground prose-p:text-foreground/90 prose-a:text-primary prose-strong:text-foreground prose-code:text-foreground prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-muted">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      {/* Mobile citations toggle */}
      {result.citations && result.citations.length > 0 && (
        <div className="lg:hidden border-l-0 border-t">
          <button
            onClick={() => setShowMobileCitations(!showMobileCitations)}
            className="w-full px-4 py-2.5 flex items-center justify-between text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="font-medium">Citations ({result.citations.length})</span>
            <ChevronDown className={cn('w-4 h-4 transition-transform', showMobileCitations && 'rotate-180')} />
          </button>
          {showMobileCitations && (
            <div className="px-4 pb-4 space-y-2 animate-fade-in">
              {result.citations.map((citation, index) => (
                <div key={index} className="p-3 rounded-lg border text-sm">
                  <p className="font-medium text-foreground text-xs">{citation.title}</p>
                  {citation.url && (
                    <a href={citation.url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-primary hover:underline inline-flex items-center gap-0.5 mt-0.5">
                      <ExternalLink className="w-2.5 h-2.5" />
                      {(() => { try { return new URL(citation.url).hostname } catch { return citation.url } })()}
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sidebar (desktop) */}
      <div className="hidden lg:block w-80 border-l overflow-auto p-4 space-y-6">
        {/* Citations */}
        {result.citations && result.citations.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
              Citations ({result.citations.length})
            </h3>
            <div className="space-y-2">
              {result.citations.map((citation, index) => (
                <div
                  key={index}
                  className={cn(
                    'p-3 rounded-lg border text-sm transition-colors cursor-pointer',
                    activeCitation === index ? 'border-primary bg-primary/5' : 'hover:bg-accent/50'
                  )}
                  onClick={() => setActiveCitation(activeCitation === index ? null : index)}
                >
                  <div className="flex items-start gap-2">
                    <span className="flex-shrink-0 w-5 h-5 bg-primary/10 text-primary rounded text-[10px] font-semibold flex items-center justify-center">
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="font-medium text-foreground text-xs line-clamp-2">{citation.title}</p>
                      {citation.url && (
                        <a
                          href={citation.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-primary hover:underline inline-flex items-center gap-0.5 mt-0.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="w-2.5 h-2.5" />
                          {(() => { try { return new URL(citation.url).hostname } catch { return citation.url } })()}
                        </a>
                      )}
                      {activeCitation === index && citation.snippet && (
                        <p className="text-xs text-muted-foreground mt-2">{citation.snippet}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">Metadata</h3>
          <div className="space-y-2">
            {[
              { label: 'Job ID', value: result.id.slice(0, 12) + '...', icon: Hash },
              { label: 'Model', value: result.model, icon: FileText },
              { label: 'Cost', value: formatCurrency(result.cost), icon: DollarSign },
              { label: 'Completed', value: new Date(result.completed_at).toLocaleString(), icon: Clock },
              { label: 'Content', value: `${(result.content.length / 1000).toFixed(1)}k chars`, icon: BookOpen },
              { label: 'Web Search', value: result.enable_web_search ? 'Enabled' : 'Disabled', icon: Search },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between text-xs">
                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <item.icon className="w-3 h-3" />
                  {item.label}
                </span>
                <span className="text-foreground font-medium">{item.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tags */}
        {result.tags && result.tags.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">Tags</h3>
            <div className="flex flex-wrap gap-1">
              {result.tags.map((tag) => (
                <span key={tag} className="px-2 py-0.5 bg-secondary rounded text-xs text-muted-foreground">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
