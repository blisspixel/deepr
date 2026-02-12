import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { formatCurrency, formatRelativeTime } from '@/lib/utils'
import { expertsApi } from '@/api/experts'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  FileText,
  Lightbulb,
  Loader2,
  MessageSquare,
  Plus,
  Search,
  Users,
} from 'lucide-react'

export default function ExpertHub() {
  const navigate = useNavigate()

  const { data: experts, isLoading, isError, refetch } = useQuery({
    queryKey: ['experts'],
    queryFn: expertsApi.list,
  })

  const handleCreateExpert = () => {
    toast.info('Create experts via CLI', {
      description: 'deepr expert make "Name" --files docs/*.md',
      duration: 6000,
    })
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <Users className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Failed to load experts</p>
        <p className="text-sm text-muted-foreground mb-4">Check that the Deepr backend is running.</p>
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
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Experts</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Domain experts and knowledge management</p>
        </div>
        <Button onClick={handleCreateExpert}>
          <Plus className="w-4 h-4" />
          Create Expert
        </Button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : !experts || experts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Users className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <h3 className="text-base font-medium text-foreground mb-1">No experts yet</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Create domain experts to build persistent knowledge bases.
          </p>
          <Button onClick={handleCreateExpert}>
            <Plus className="w-4 h-4" />
            Create Your First Expert
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {experts.map((expert) => (
            <div
              key={expert.name}
              className="rounded-lg border bg-card hover:border-primary/20 transition-all cursor-pointer group"
              onClick={() => navigate(`/experts/${encodeURIComponent(expert.name)}`)}
            >
              <div className="p-5 space-y-4">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <Users className="w-5 h-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                      {expert.name}
                    </h3>
                    {expert.description && (
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{expert.description}</p>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center">
                    <div className="flex items-center justify-center gap-1 text-muted-foreground mb-0.5">
                      <FileText className="w-3 h-3" />
                    </div>
                    <p className="text-sm font-semibold text-foreground tabular-nums">{expert.document_count}</p>
                    <p className="text-[10px] text-muted-foreground">Docs</p>
                  </div>
                  <div className="text-center">
                    <div className="flex items-center justify-center gap-1 text-muted-foreground mb-0.5">
                      <Lightbulb className="w-3 h-3" />
                    </div>
                    <p className="text-sm font-semibold text-foreground tabular-nums">{expert.finding_count}</p>
                    <p className="text-[10px] text-muted-foreground">Findings</p>
                  </div>
                  <div className="text-center">
                    <div className="flex items-center justify-center gap-1 text-muted-foreground mb-0.5">
                      <Search className="w-3 h-3" />
                    </div>
                    <p className="text-sm font-semibold text-foreground tabular-nums">{expert.gap_count}</p>
                    <p className="text-[10px] text-muted-foreground">Gaps</p>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-3 border-t text-xs text-muted-foreground">
                  <span>{formatCurrency(expert.total_cost)} total</span>
                  <span>{expert.last_active ? formatRelativeTime(expert.last_active) : 'Never'}</span>
                </div>

                <div className="flex gap-2">
                  <button
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs font-medium hover:bg-secondary/80 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/experts/${encodeURIComponent(expert.name)}`)
                    }}
                  >
                    <MessageSquare className="w-3 h-3" />
                    Chat
                  </button>
                  <button
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs font-medium hover:bg-secondary/80 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/experts/${encodeURIComponent(expert.name)}?tab=gaps`)
                    }}
                  >
                    <Search className="w-3 h-3" />
                    Gaps
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
