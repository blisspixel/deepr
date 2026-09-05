import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { expertsApi } from '@/api/experts'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Plus, Search, Users } from 'lucide-react'
import { CardGridSkeleton } from '@/components/ui/skeleton'
import { ExpertPortrait } from '@/components/expert-portrait'

export default function ExpertHub() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState('formed')
  const [rosterView, setRosterView] = useState<'flagship' | 'all' | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [newExpert, setNewExpert] = useState({ name: '', description: '', domain: '' })

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data: experts, isLoading, isError, refetch } = useQuery({
    queryKey: ['experts'],
    queryFn: expertsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: expertsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experts'] })
      setRosterView('all')
      setSearchQuery('')
      setDebouncedSearch('')
      setCreateOpen(false)
      setNewExpert({ name: '', description: '', domain: '' })
      toast.success('Expert created')
    },
    onError: () => {
      toast.error('Failed to create expert')
    },
  })

  const handleCreateExpert = () => setCreateOpen(true)

  const handleSubmitCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newExpert.name.trim()) return
    createMutation.mutate({
      name: newExpert.name.trim(),
      description: newExpert.description.trim() || undefined,
      domain: newExpert.domain.trim() || undefined,
    })
  }

  const flagshipCount = experts?.filter(e => e.roster_tier === 'flagship').length ?? 0
  const flagshipReadyCount =
    experts?.filter(e => e.roster_tier === 'flagship' && e.roster_ready).length ?? 0
  const allReadyCount = experts?.filter(e => e.roster_ready).length ?? 0
  const effectiveRosterView = rosterView ?? (flagshipCount > 0 ? 'flagship' : 'all')

  const filteredExperts = useMemo(() => {
    if (!experts) return []
    let filtered = effectiveRosterView === 'flagship'
      ? experts.filter(e => e.roster_tier === 'flagship')
      : [...experts]
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      filtered = filtered.filter(e =>
        e.name.toLowerCase().includes(q) ||
        e.description?.toLowerCase().includes(q)
      )
    }
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'positions': return (b.position_count ?? 0) - (a.position_count ?? 0)
        case 'docs': return b.document_count - a.document_count
        case 'recent': return (b.last_active || '').localeCompare(a.last_active || '')
        case 'name': return a.name.localeCompare(b.name)
        default:
          // An expert that has read something and landed somewhere leads.
          // Alphabetical put "Agentic Development Loops" - which has never
          // been studied - above every expert that actually holds a view, so
          // the roster opened on its emptiest rows.
          return (
            (b.roster_ready ? 1 : 0) - (a.roster_ready ? 1 : 0) ||
            (b.position_count ?? 0) - (a.position_count ?? 0) ||
            (b.standpoint ? 1 : 0) - (a.standpoint ? 1 : 0) ||
            (b.studied_findings ?? b.finding_count) - (a.studied_findings ?? a.finding_count) ||
            a.name.localeCompare(b.name)
          )
      }
    })
    return filtered
  }, [experts, debouncedSearch, effectiveRosterView, sortBy])

  if (isLoading) return <div role="status" aria-label="Loading experts"><CardGridSkeleton /></div>

  if (isError) {
    return (
      <div role="alert" className="flex min-h-[60vh] flex-col items-center justify-center p-4 text-center">
        <Users className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Unable to load experts</p>
        <p className="text-sm text-muted-foreground mb-4">The server could not return your experts. This does not mean the workspace is empty.</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary-hover transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-foreground">Experts</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {flagshipCount > 0 && <>{flagshipCount} flagship &middot; </>}{experts?.length ?? 0} total &middot;{' '}
            {effectiveRosterView === 'flagship'
              ? `${flagshipReadyCount} of ${flagshipCount} flagship ready`
              : `${allReadyCount} presentation-ready`}
          </p>
        </div>
        <Button onClick={handleCreateExpert}>
          <Plus className="w-4 h-4" />
          Create Expert
        </Button>
      </div>

      {/* Search + Sort */}
      {experts && experts.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search experts..."
              aria-label="Search experts"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-full sm:w-[180px]" aria-label="Sort experts">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="formed">Most formed</SelectItem>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="positions">Most positions</SelectItem>
              <SelectItem value="docs">Most documents</SelectItem>
              <SelectItem value="recent">Most recent</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={effectiveRosterView}
            onValueChange={(value) => setRosterView(value as 'flagship' | 'all')}
          >
            <SelectTrigger className="w-full sm:w-[170px]" aria-label="Roster view">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="flagship">Flagship roster</SelectItem>
              <SelectItem value="all">All experts</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Content */}
      {!experts || experts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Users className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <h3 className="text-base font-medium text-foreground mb-1">No experts yet</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Create a local expert profile, then add trusted sources with the CLI. No API key is needed.
          </p>
          <Button onClick={handleCreateExpert}>
            <Plus className="w-4 h-4" />
            Create Your First Expert
          </Button>
        </div>
      ) : filteredExperts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Search className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <h3 className="text-base font-medium text-foreground mb-1">
            {effectiveRosterView === 'flagship' && !debouncedSearch ? 'No flagship experts yet' : 'No matches'}
          </h3>
          <p className="text-sm text-muted-foreground">
            {effectiveRosterView === 'flagship' && !debouncedSearch
              ? 'Feature experts explicitly, or switch to the complete roster.'
              : `No experts match "${debouncedSearch}".`}
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => {
              setSearchQuery('')
              setDebouncedSearch('')
              setRosterView('all')
            }}
          >
            Show all experts
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
          {filteredExperts.map((expert) => (
            <Link
              key={expert.name}
              to={`/experts/${encodeURIComponent(expert.name)}`}
              className="rounded-lg border bg-card hover:border-primary/20 hover:shadow-md transition-all group focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <div className="p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <ExpertPortrait
                    name={expert.name}
                    portraitUrl={expert.portrait_url}
                    className="w-11 h-11 rounded-md shrink-0"
                    iconClassName="w-5 h-5"
                  />
                  <div className="min-w-0">
                    {/* The name it chose leads; the subject it is filed under
                        is the subtitle. An expert that named itself Marlowe is
                        a someone to ask, and "Temporal Knowledge Graphs" is
                        the shelf it sits on. */}
                    <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                      {expert.chosen_name || expert.name}
                    </h3>
                    <p className="text-2xs uppercase text-muted-foreground mt-0.5 truncate">
                      {expert.chosen_name ? expert.name : expert.description}
                    </p>
                  </div>
                </div>

                {/*
                  A tile answers "expert on what, and how formed" - nothing
                  more. The standpoint and what it is glad to be asked live on
                  the expert's own page, one click away.

                  They were on the tile, and a quoted block with a coloured
                  left rule repeated down a grid reads as decoration however
                  good the sentence inside it is.
                */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span title="Positions held, each stating what would overturn it">
                    <span className="data-figure text-foreground">{expert.position_count ?? 0}</span> positions
                  </span>
                  <span title="Findings from its own study of the retained corpus">
                    <span className="data-figure text-foreground">
                      {expert.studied_findings ?? 0}
                    </span>{' '}
                    findings
                  </span>
                  {(expert.source_count ?? 0) > 0 && (
                    <span title="Independent sources retained">
                      <span className="data-figure text-foreground">{expert.source_count}</span> sources
                    </span>
                  )}
                  {(expert.mind_changes ?? 0) > 0 && (
                    <span title="Recorded changes of mind, with what moved each one">
                      <span className="data-figure text-foreground">{expert.mind_changes}</span> shifts
                    </span>
                  )}
                  {!expert.standpoint && <span className="text-warning">no standpoint yet</span>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Create Expert Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <form onSubmit={handleSubmitCreate}>
            <DialogHeader>
              <DialogTitle>Create Expert</DialogTitle>
              <DialogDescription>
                Create a local profile without a model call. Add trusted sources later with the local CLI.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-1.5">
                <Label htmlFor="expert-name">Name *</Label>
                <Input
                  id="expert-name"
                  placeholder="e.g. Climate Science"
                  value={newExpert.name}
                  onChange={(e) => setNewExpert(prev => ({ ...prev, name: e.target.value }))}
                  maxLength={200}
                  autoFocus
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="expert-description">Description</Label>
                <Input
                  id="expert-description"
                  placeholder="What this expert knows about"
                  value={newExpert.description}
                  onChange={(e) => setNewExpert(prev => ({ ...prev, description: e.target.value }))}
                  maxLength={1000}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="expert-domain">Domain</Label>
                <Input
                  id="expert-domain"
                  placeholder="e.g. science, engineering, economics"
                  value={newExpert.domain}
                  onChange={(e) => setNewExpert(prev => ({ ...prev, domain: e.target.value }))}
                  maxLength={200}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!newExpert.name.trim() || createMutation.isPending} loading={createMutation.isPending}>
                Create
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
