import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formatCurrency, formatRelativeTime } from '@/lib/utils'
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
import {
  FileText,
  Lightbulb,
  MessageSquare,
  Plus,
  Search,
  Users,
} from 'lucide-react'
import { CardGridSkeleton } from '@/components/ui/skeleton'

export default function ExpertHub() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState('name')
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

  const filteredExperts = useMemo(() => {
    if (!experts) return []
    let filtered = [...experts]
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      filtered = filtered.filter(e =>
        e.name.toLowerCase().includes(q) ||
        e.description?.toLowerCase().includes(q)
      )
    }
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'docs': return b.document_count - a.document_count
        case 'cost': return b.total_cost - a.total_cost
        case 'recent': return (b.last_active || '').localeCompare(a.last_active || '')
        default: return a.name.localeCompare(b.name)
      }
    })
    return filtered
  }, [experts, debouncedSearch, sortBy])

  if (isLoading) return <CardGridSkeleton />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <Users className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Unable to load experts</p>
        <p className="text-sm text-muted-foreground mb-4">Could not connect to the backend. Experts will appear here once the server is running.</p>
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
          <h1 className="text-2xl font-semibold text-foreground">Experts</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Domain experts and knowledge management</p>
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
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="docs">Most Documents</SelectItem>
              <SelectItem value="cost">Highest Cost</SelectItem>
              <SelectItem value="recent">Most Recent</SelectItem>
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
            Create domain experts to build persistent knowledge bases.
          </p>
          <Button onClick={handleCreateExpert}>
            <Plus className="w-4 h-4" />
            Create Your First Expert
          </Button>
        </div>
      ) : filteredExperts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Search className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <h3 className="text-base font-medium text-foreground mb-1">No matches</h3>
          <p className="text-sm text-muted-foreground">No experts match "{debouncedSearch}".</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredExperts.map((expert) => (
            <div
              key={expert.name}
              className="rounded-lg border bg-card hover:border-primary/20 hover:shadow-md transition-all cursor-pointer group"
              onClick={() => navigate(`/experts/${encodeURIComponent(expert.name)}`)}
            >
              <div className="p-5 space-y-4">
                <div className="flex items-start gap-3">
                  {expert.portrait_url ? (
                    <img
                      src={expert.portrait_url}
                      alt={`${expert.name} portrait`}
                      className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Users className="w-5 h-5 text-primary" />
                    </div>
                  )}
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

      {/* Create Expert Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <form onSubmit={handleSubmitCreate}>
            <DialogHeader>
              <DialogTitle>Create Expert</DialogTitle>
              <DialogDescription>
                Create a new domain expert. You can add documents later via CLI.
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
