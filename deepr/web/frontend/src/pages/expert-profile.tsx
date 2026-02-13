import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { cn, formatCurrency, formatRelativeTime } from '@/lib/utils'
import { expertsApi } from '@/api/experts'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import type { ExpertChat } from '@/types'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Clock,
  DollarSign,
  FileText,
  GitBranch,
  Lightbulb,
  Loader2,
  MessageSquare,
  Search,
  SearchX,
  Send,
  Shield,
  Users,
} from 'lucide-react'
import { DetailSkeleton } from '@/components/ui/skeleton'

type TabKey = 'chat' | 'claims' | 'gaps' | 'decisions' | 'history'

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full',
            value >= 0.8 ? 'bg-green-500' : value >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground tabular-nums">{pct}%</span>
    </div>
  )
}

function EvScoreBadge({ ratio }: { ratio: number }) {
  return (
    <span className={cn(
      'px-1.5 py-0.5 rounded text-[10px] font-semibold tabular-nums',
      ratio > 1.0 ? 'bg-green-500/10 text-green-600' :
      ratio >= 0.5 ? 'bg-yellow-500/10 text-yellow-600' :
      'bg-red-500/10 text-red-600'
    )}>
      {ratio.toFixed(2)}
    </span>
  )
}

const DECISION_TYPE_ICONS: Record<string, typeof GitBranch> = {
  routing: GitBranch,
  stop: CheckCircle,
  pivot: GitBranch,
  budget: DollarSign,
  belief_revision: Lightbulb,
  gap_fill: Search,
  conflict_resolution: Shield,
  source_selection: FileText,
}

export default function ExpertProfile() {
  const { name } = useParams<{ name: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const initialTab = (searchParams.get('tab') as TabKey) || 'chat'
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab)
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<(ExpertChat & { error?: boolean })[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)

  const decodedName = decodeURIComponent(name || '')
  const encodedName = encodeURIComponent(decodedName)

  // Reset chat when switching experts
  useEffect(() => {
    setChatMessages([])
    setChatInput('')
  }, [decodedName])

  const { data: expert, isLoading, isError, refetch } = useQuery({
    queryKey: ['experts', decodedName],
    queryFn: () => expertsApi.get(encodedName),
    enabled: !!decodedName,
  })

  const { data: gaps, isLoading: isGapsLoading } = useQuery({
    queryKey: ['experts', decodedName, 'gaps'],
    queryFn: () => expertsApi.getGaps(encodedName),
    enabled: !!decodedName && activeTab === 'gaps',
  })

  const { data: claims, isLoading: isClaimsLoading } = useQuery({
    queryKey: ['experts', decodedName, 'claims'],
    queryFn: () => expertsApi.getClaims(encodedName),
    enabled: !!decodedName && activeTab === 'claims',
  })

  const { data: decisions, isLoading: isDecisionsLoading } = useQuery({
    queryKey: ['experts', decodedName, 'decisions'],
    queryFn: () => expertsApi.getDecisions(encodedName),
    enabled: !!decodedName && activeTab === 'decisions',
  })

  const { data: history } = useQuery({
    queryKey: ['experts', decodedName, 'history'],
    queryFn: () => expertsApi.getHistory(encodedName) as Promise<{ id: string; type: string; description: string; timestamp: string; cost?: number }[]>,
    enabled: !!decodedName && activeTab === 'history',
  })

  const chatMutation = useMutation({
    mutationFn: (message: string) => expertsApi.chat(encodedName, message),
    onSuccess: (data) => {
      setChatMessages(prev => [...prev, data])
    },
    onError: () => {
      setChatMessages(prev => {
        const updated = [...prev]
        if (updated.length > 0) {
          updated[updated.length - 1] = { ...updated[updated.length - 1], error: true }
        }
        return updated
      })
      toast.error('Failed to get response from expert')
    },
  })

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatInput.trim()) return
    setChatMessages(prev => [...prev, { role: 'user', content: chatInput, timestamp: new Date().toISOString() }])
    chatMutation.mutate(chatInput)
    setChatInput('')
  }

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  if (isLoading) return <DetailSkeleton />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <AlertTriangle className="w-10 h-10 text-destructive mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Failed to load expert</p>
        <p className="text-sm text-muted-foreground mb-4">Something went wrong fetching this expert profile.</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!expert) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <Users className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Expert not found</p>
        <button onClick={() => navigate('/experts')} className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
          Back to Experts
        </button>
      </div>
    )
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'chat', label: 'Chat' },
    { key: 'claims', label: 'Claims' },
    { key: 'gaps', label: 'Knowledge Gaps' },
    { key: 'decisions', label: 'Decisions' },
    { key: 'history', label: 'History' },
  ]

  const sortedClaims = claims
    ? [...claims].sort((a, b) => b.confidence - a.confidence)
    : []

  const sortedDecisions = decisions
    ? [...decisions].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    : []

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] animate-fade-in">
      {/* Header */}
      <div className="p-6 border-b space-y-4 flex-shrink-0">
        <button
          onClick={() => navigate('/experts')}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Experts
        </button>

        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <Users className="w-6 h-6 text-primary" />
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-semibold text-foreground">{expert.name}</h1>
            {expert.description && <p className="text-sm text-muted-foreground mt-0.5">{expert.description}</p>}
            <div className="flex flex-wrap items-center gap-4 mt-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1"><FileText className="w-3 h-3" />{expert.document_count} docs</span>
              <span className="inline-flex items-center gap-1"><Lightbulb className="w-3 h-3" />{expert.finding_count} findings</span>
              <span className="inline-flex items-center gap-1"><Search className="w-3 h-3" />{expert.gap_count} gaps</span>
              <span className="inline-flex items-center gap-1"><DollarSign className="w-3 h-3" />{formatCurrency(expert.total_cost)}</span>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-secondary rounded-lg w-fit">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'px-4 py-1.5 rounded-md text-xs font-medium transition-all',
                activeTab === tab.key
                  ? 'bg-background shadow-sm text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'chat' && (
          <div className="flex flex-col h-full">
            {/* Messages */}
            <div className="flex-1 overflow-auto p-6 space-y-4">
              {chatMessages.length === 0 && (
                <div className="flex flex-col items-center justify-center text-center py-12">
                  <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
                    <MessageSquare className="w-6 h-6 text-muted-foreground" />
                  </div>
                  <h3 className="text-sm font-medium text-foreground mb-1">Start a conversation</h3>
                  <p className="text-xs text-muted-foreground max-w-xs">
                    Ask {expert.name} questions about their domain expertise.
                  </p>
                </div>
              )}
              {chatMessages.map((msg, index) => (
                <div key={index} className={cn('flex gap-3', msg.role === 'user' && 'justify-end')}>
                  <div className={cn(
                    'max-w-[70%] rounded-lg p-3 text-sm',
                    msg.role === 'user'
                      ? msg.error ? 'bg-destructive/10 text-foreground border border-destructive/30' : 'bg-primary text-primary-foreground'
                      : 'bg-secondary text-foreground'
                  )}>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    <div className={cn(
                      'flex items-center gap-2 text-[10px] mt-1',
                      msg.role === 'user' ? (msg.error ? 'text-destructive' : 'text-primary-foreground/60') : 'text-muted-foreground'
                    )}>
                      <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                      {msg.error && <span>Failed to send</span>}
                    </div>
                  </div>
                </div>
              ))}
              {chatMutation.isPending && (
                <div className="flex gap-3">
                  <div className="bg-secondary rounded-lg p-3">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <form onSubmit={handleSendMessage} className="p-4 border-t flex gap-2">
              <Input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder={`Ask ${expert.name} a question...`}
                className="flex-1"
              />
              <Button
                type="submit"
                size="icon"
                disabled={!chatInput.trim()}
                loading={chatMutation.isPending}
                aria-label="Send message"
              >
                <Send className="w-4 h-4" />
              </Button>
            </form>
          </div>
        )}

        {activeTab === 'claims' && (
          <div className="p-6">
            {isClaimsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : !sortedClaims.length ? (
              <div className="flex flex-col items-center justify-center text-center py-12">
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
                  <Lightbulb className="w-6 h-6 text-muted-foreground" />
                </div>
                <h3 className="text-sm font-medium text-foreground mb-1">No claims yet</h3>
                <p className="text-xs text-muted-foreground max-w-xs">
                  Claims will appear here as the expert forms beliefs from evidence.
                </p>
              </div>
            ) : (
              <div className="rounded-lg border bg-card overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left p-3 font-medium text-muted-foreground">Statement</th>
                      <th className="text-left p-3 font-medium text-muted-foreground w-32">Confidence</th>
                      <th className="text-left p-3 font-medium text-muted-foreground w-20">Sources</th>
                      <th className="text-left p-3 font-medium text-muted-foreground w-28">Domain</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedClaims.map((claim) => (
                      <tr key={claim.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="p-3 text-foreground">{claim.statement}</td>
                        <td className="p-3"><ConfidenceBar value={claim.confidence} /></td>
                        <td className="p-3">
                          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-secondary text-xs font-medium text-foreground">
                            {claim.sources.length}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 rounded bg-secondary text-xs text-muted-foreground">
                            {claim.domain}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'gaps' && (
          <div className="p-6 space-y-3">
            {isGapsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : !gaps || gaps.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-12">
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
                  <SearchX className="w-6 h-6 text-muted-foreground" />
                </div>
                <h3 className="text-sm font-medium text-foreground mb-1">No knowledge gaps</h3>
                <p className="text-xs text-muted-foreground max-w-xs">
                  Knowledge gaps will appear here as the expert identifies areas needing more research.
                </p>
              </div>
            ) : (
              gaps.map((gap) => (
                <div key={gap.id} className="rounded-lg border bg-card p-4 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-foreground">{gap.topic}</h3>
                      {gap.questions.length > 0 && (
                        <ul className="mt-1 space-y-0.5">
                          {gap.questions.map((q, i) => (
                            <li key={i} className="text-xs text-muted-foreground">- {q}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <EvScoreBadge ratio={gap.ev_cost_ratio} />
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-secondary text-muted-foreground">
                        P{gap.priority}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span>EV: {gap.expected_value.toFixed(2)}</span>
                    <span>Cost: {formatCurrency(gap.estimated_cost)}</span>
                    {gap.times_asked > 0 && <span>Asked {gap.times_asked}x</span>}
                    {gap.filled && <span className="text-green-600">Filled</span>}
                  </div>
                  <button
                    className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary rounded text-xs font-medium hover:bg-primary/20 transition-colors"
                    onClick={() => navigate(`/research?prompt=${encodeURIComponent(gap.topic)}`)}
                  >
                    <Search className="w-3 h-3" />
                    Research this
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'decisions' && (
          <div className="p-6 space-y-3">
            {isDecisionsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : !sortedDecisions.length ? (
              <div className="flex flex-col items-center justify-center text-center py-12">
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
                  <GitBranch className="w-6 h-6 text-muted-foreground" />
                </div>
                <h3 className="text-sm font-medium text-foreground mb-1">No decisions yet</h3>
                <p className="text-xs text-muted-foreground max-w-xs">
                  Decision records will appear here as the expert makes research decisions.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {sortedDecisions.map((dec) => {
                  const Icon = DECISION_TYPE_ICONS[dec.decision_type] || GitBranch
                  return (
                    <div key={dec.id} className="rounded-lg border bg-card p-4 space-y-2">
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <Icon className="w-4 h-4 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-sm font-medium text-foreground">{dec.title}</h3>
                            <span className="px-1.5 py-0.5 rounded bg-secondary text-[10px] font-medium text-muted-foreground">
                              {dec.decision_type}
                            </span>
                            <ConfidenceBar value={dec.confidence} />
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">{dec.rationale}</p>
                          <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground">
                            <span>{formatRelativeTime(dec.timestamp)}</span>
                            {dec.cost_impact !== 0 && (
                              <span>Cost: {formatCurrency(Math.abs(dec.cost_impact))}</span>
                            )}
                            {dec.alternatives.length > 0 && (
                              <span>{dec.alternatives.length} alternatives</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="p-6 space-y-3">
            {!history || history.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-12">
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
                  <Clock className="w-6 h-6 text-muted-foreground" />
                </div>
                <h3 className="text-sm font-medium text-foreground mb-1">No activity yet</h3>
                <p className="text-xs text-muted-foreground max-w-xs">
                  Learning events and research activity will be logged here.
                </p>
              </div>
            ) : (
              history.map((event) => (
                <div key={event.id} className="flex items-start gap-3 text-sm">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-foreground">{event.description}</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                      <span>{formatRelativeTime(event.timestamp)}</span>
                      {event.cost && <span>{formatCurrency(event.cost)}</span>}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
