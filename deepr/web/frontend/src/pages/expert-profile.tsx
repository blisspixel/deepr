import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { cn, formatCurrency, formatRelativeTime } from '@/lib/utils'
import { expertsApi } from '@/api/experts'
import { toast } from 'sonner'
import type { ExpertChat } from '@/types'
import {
  ArrowLeft,
  DollarSign,
  FileText,
  Lightbulb,
  Loader2,
  Search,
  Send,
  Users,
} from 'lucide-react'

export default function ExpertProfile() {
  const { name } = useParams<{ name: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const initialTab = (searchParams.get('tab') as 'chat' | 'gaps' | 'history') || 'chat'
  const [activeTab, setActiveTab] = useState<'chat' | 'gaps' | 'history'>(initialTab)
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<ExpertChat[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)

  const decodedName = decodeURIComponent(name || '')
  const encodedName = encodeURIComponent(decodedName)

  const { data: expert, isLoading } = useQuery({
    queryKey: ['experts', decodedName],
    queryFn: () => expertsApi.get(encodedName),
    enabled: !!decodedName,
  })

  const { data: gaps, isLoading: isGapsLoading } = useQuery({
    queryKey: ['experts', decodedName, 'gaps'],
    queryFn: () => expertsApi.getGaps(encodedName),
    enabled: !!decodedName && activeTab === 'gaps',
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
      // Remove the user message that was optimistically added
      setChatMessages(prev => prev.slice(0, -1))
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
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

  const tabs = [
    { key: 'chat' as const, label: 'Chat' },
    { key: 'gaps' as const, label: 'Knowledge Gaps' },
    { key: 'history' as const, label: 'History' },
  ]

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)]">
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
                <div className="text-center text-muted-foreground text-sm py-12">
                  Start a conversation with {expert.name}. Ask questions about their domain expertise.
                </div>
              )}
              {chatMessages.map((msg, index) => (
                <div key={index} className={cn('flex gap-3', msg.role === 'user' && 'justify-end')}>
                  <div className={cn(
                    'max-w-[70%] rounded-lg p-3 text-sm',
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-secondary text-foreground'
                  )}>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    <p className={cn(
                      'text-[10px] mt-1',
                      msg.role === 'user' ? 'text-primary-foreground/60' : 'text-muted-foreground'
                    )}>
                      {new Date(msg.timestamp).toLocaleTimeString()}
                    </p>
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
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder={`Ask ${expert.name} a question...`}
                className="flex-1 px-3 py-2 bg-background border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
              />
              <button
                type="submit"
                disabled={!chatInput.trim() || chatMutation.isPending}
                className="px-3 py-2 bg-primary text-primary-foreground rounded-lg disabled:opacity-50 transition-colors hover:bg-primary/90"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        )}

        {activeTab === 'gaps' && (
          <div className="p-6 space-y-3">
            {isGapsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : !gaps || gaps.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm py-12">
                No knowledge gaps identified yet.
              </div>
            ) : (
              gaps.map((gap) => (
                <div key={gap.id} className="rounded-lg border bg-card p-4 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">{gap.topic}</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">{gap.description}</p>
                    </div>
                    <span className={cn(
                      'px-2 py-0.5 rounded text-[10px] font-semibold uppercase',
                      gap.priority === 'high' && 'bg-destructive/10 text-destructive',
                      gap.priority === 'medium' && 'bg-warning/10 text-warning',
                      gap.priority === 'low' && 'bg-muted text-muted-foreground'
                    )}>
                      {gap.priority}
                    </span>
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

        {activeTab === 'history' && (
          <div className="p-6 space-y-3">
            {!history || history.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm py-12">
                No learning history yet.
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
