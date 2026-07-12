import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { cn, formatCurrency, formatRelativeTime } from '@/lib/utils'
import { expertsApi } from '@/api/experts'
import { costApi } from '@/api/cost'
import { wsClient } from '@/api/websocket'
import { toast } from 'sonner'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { MarkdownMessage } from '@/components/chat/markdown-message'
import { ToolCallBlock } from '@/components/chat/tool-call-block'
import { MessageActions } from '@/components/chat/message-actions'
import { SlashCommandMenu } from '@/components/chat/slash-command-menu'
import { ThinkingPanel } from '@/components/chat/thinking-panel'
import { CompactBanner } from '@/components/chat/compact-banner'
import { ConfirmDialog } from '@/components/chat/confirm-dialog'
import { PlanDisplay } from '@/components/chat/plan-display'
import { CHAT_MODES } from '@/lib/constants'
import {
  browserExpertChatFailureMessage,
  clampBrowserExpertChatBudgetInput,
  prepareBrowserExpertChatRequest,
  type BrowserExpertChatRequestPayload,
} from '@/lib/expert-chat-contract'
import type { ExpertChat, Skill, SupportClass, ChatMode, ThoughtItem, ConfirmRequest, PlanStep } from '@/types'
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
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
  Sparkles,
  Square,
  Users,
} from 'lucide-react'
import { DetailSkeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/shared/empty-state'
import PartialQueryError from '@/components/shared/partial-query-error'
import { ExpertPortrait } from '@/components/expert-portrait'

type TabKey = 'chat' | 'claims' | 'gaps' | 'decisions' | 'history' | 'skills'

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

const SUPPORT_CLASS_STYLES: Record<SupportClass, { bg: string; text: string; label: string }> = {
  supported: { bg: 'bg-green-500/10', text: 'text-green-600', label: 'Supported' },
  partially_supported: { bg: 'bg-yellow-500/10', text: 'text-yellow-600', label: 'Partial' },
  unsupported: { bg: 'bg-red-500/10', text: 'text-red-600', label: 'Unsupported' },
  uncertain: { bg: 'bg-gray-500/10', text: 'text-gray-500', label: 'Uncertain' },
}

function SupportClassBadge({ support }: { support: SupportClass }) {
  const style = SUPPORT_CLASS_STYLES[support]
  return (
    <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-semibold', style.bg, style.text)}>
      {style.label}
    </span>
  )
}

function SkillCard({ skill, action, installed }: { skill: Skill; action: React.ReactNode; installed?: boolean }) {
  return (
    <div className={cn(
      'rounded-lg border p-4 flex items-center gap-4',
      installed ? 'bg-card' : 'border-dashed bg-card/50',
    )}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-medium text-foreground">{skill.name}</h4>
          {installed && (
            <span className="px-1.5 py-0.5 rounded bg-secondary text-[10px] font-medium text-muted-foreground">
              v{skill.version}
            </span>
          )}
          <span className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-semibold',
            skill.tier === 'built-in' ? 'bg-blue-500/10 text-blue-600' :
            skill.tier === 'global' ? 'bg-purple-500/10 text-purple-600' :
            'bg-green-500/10 text-green-600'
          )}>
            {skill.tier}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{skill.description}</p>
        <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground">
          <span>{skill.tools} tool{skill.tools !== 1 ? 's' : ''}</span>
          {skill.domains.length > 0 && <span>{skill.domains.join(', ')}</span>}
        </div>
      </div>
      {action}
    </div>
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
  const [chatMessages, setChatMessages] = useState<ExpertChat[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [activeTools, setActiveTools] = useState<{ tool: string; query: string; startedAt: number }[]>([])
  const [chatMode, setChatMode] = useState<ChatMode>('research')
  const [chatBudgetInput, setChatBudgetInput] = useState('')
  const [meteredChatConfirmed, setMeteredChatConfirmed] = useState(false)
  const [socketSessionActive, setSocketSessionActive] = useState(false)
  const [thoughts, setThoughts] = useState<ThoughtItem[]>([])
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const [compactSuggest, setCompactSuggest] = useState<{ messageCount: number } | null>(null)
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null)
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([])
  const [planQuery, setPlanQuery] = useState('')
  const chatEndRef = useRef<HTMLDivElement>(null)
  const userScrolledRef = useRef(false)
  const streamingContentRef = useRef('')

  const decodedName = decodeURIComponent(name || '')
  const encodedName = encodeURIComponent(decodedName)

  // Reset chat when switching experts
  useEffect(() => {
    wsClient.endChat()
    setChatMessages([])
    setChatInput('')
    setSessionId(null)
    setIsStreaming(false)
    setIsStopping(false)
    setStreamingContent('')
    streamingContentRef.current = ''
    setActiveTools([])
    setSocketSessionActive(false)
    setMeteredChatConfirmed(false)
  }, [decodedName])

  // Wire Socket.IO chat events
  useEffect(() => {
    const cleanups = [
      wsClient.onChatToken(({ content }) => {
        streamingContentRef.current += content
        setStreamingContent(prev => prev + content)
      }),
      wsClient.onChatToolStart(({ tool, query }) => {
        setActiveTools(prev => [...prev, { tool, query, startedAt: Date.now() }])
      }),
      wsClient.onChatToolEnd(({ tool }) => {
        setActiveTools(prev => {
          const idx = prev.findIndex(t => t.tool === tool)
          return idx >= 0 ? [...prev.slice(0, idx), ...prev.slice(idx + 1)] : prev
        })
      }),
      wsClient.onChatComplete((data) => {
        setIsStreaming(false)
        setIsStopping(false)
        setStreamingContent('')
        streamingContentRef.current = ''
        setActiveTools([])
        setThoughts([])
        if (data.session_id) setSessionId(data.session_id)
        if (data.mode) setChatMode(data.mode as ChatMode)
        setSocketSessionActive(true)
        setChatMessages(prev => [...prev, {
          id: data.id,
          role: 'assistant',
          content: data.content,
          timestamp: new Date().toISOString(),
          session_id: data.session_id,
          cost: data.cost,
          tool_calls: data.tool_calls,
          follow_ups: data.follow_ups,
          confidence: data.confidence,
        }])
      }),
      wsClient.onChatError(({ error, error_code, retryable }) => {
        if (error_code === 'chat_turn_in_progress') {
          toast.error(`Chat error: ${error}`)
          return
        }
        const partialContent = streamingContentRef.current
        setIsStreaming(false)
        setIsStopping(false)
        setStreamingContent('')
        streamingContentRef.current = ''
        setActiveTools([])
        setThoughts([])
        if (error_code === 'chat_turn_failed') {
          setSocketSessionActive(false)
          setMeteredChatConfirmed(false)
          setSessionId(null)
          setChatMessages(prev => [...prev, {
            role: 'assistant',
            content: browserExpertChatFailureMessage({
              error,
              retryable: Boolean(retryable),
              partialContent,
            }),
            timestamp: new Date().toISOString(),
            error: true,
          }])
        }
        toast.error(`Chat error: ${error}`)
      }),
      wsClient.onChatCancelled(({ cost_status }) => {
        const partial = streamingContentRef.current
        setIsStreaming(false)
        setIsStopping(false)
        setStreamingContent('')
        streamingContentRef.current = ''
        setActiveTools([])
        setThoughts([])
        setSocketSessionActive(false)
        setMeteredChatConfirmed(false)
        setSessionId(null)
        if (partial) {
          setChatMessages(prev => [...prev, {
            role: 'assistant',
            content: `${partial}\n\n*(stopped before completion)*`,
            timestamp: new Date().toISOString(),
          }])
        }
        if (cost_status === 'reservation_active') {
          toast.warning('Chat stopped. Cost reconciliation is still pending against the approved ceiling.')
        } else {
          toast.info('Chat stopped. Provider work was cancelled where supported and costs were closed safely.')
        }
      }),
      // Agentic events
      wsClient.onChatThought((thought) => {
        setThoughts(prev => [...prev, thought])
      }),
      wsClient.onCommandResult((result) => {
        if (result.mode) setChatMode(result.mode)
        if (result.clear_chat) {
          setChatMessages([])
          setSessionId(null)
        }
        if (result.output) {
          // Show command output as a system message
          setChatMessages(prev => [...prev, {
            role: 'assistant',
            content: result.output,
            timestamp: new Date().toISOString(),
          }])
        }
        if (result.end_session) {
          setSocketSessionActive(false)
          setMeteredChatConfirmed(false)
          setSessionId(null)
          toast.info('Chat session ended')
        }
      }),
      wsClient.on('ws_status', ({ connected }: { connected: boolean }) => {
        if (!connected) {
          const partial = streamingContentRef.current
          setIsStreaming(false)
          setIsStopping(false)
          setStreamingContent('')
          streamingContentRef.current = ''
          setActiveTools([])
          setThoughts([])
          setSocketSessionActive(false)
          setMeteredChatConfirmed(false)
          setSessionId(null)
          if (partial) {
            setChatMessages(prev => [...prev, {
              role: 'assistant',
              content: `${partial}\n\n*(connection lost before completion)*`,
              timestamp: new Date().toISOString(),
            }])
          }
        }
      }),
      wsClient.onCompactSuggest(({ message_count }) => {
        setCompactSuggest({ messageCount: message_count })
      }),
      wsClient.onCompactDone((data) => {
        setCompactSuggest(null)
        if (data.error) {
          toast.error(`Compact failed: ${data.error}`)
        } else {
          toast.success(`Compacted ${data.original_messages ?? '?'} messages`)
        }
      }),
      wsClient.onChatConfirmRequest((req) => {
        setConfirmRequest(req)
      }),
      wsClient.onChatPlan((data) => {
        setPlanQuery(data.query)
        setPlanSteps(data.steps)
      }),
      wsClient.onChatPlanStep((data) => {
        setPlanSteps(prev => prev.map(s => s.id === data.id ? { ...s, status: data.status as PlanStep['status'] } : s))
      }),
    ]
    return () => cleanups.forEach(fn => fn())
  }, [])

  const { data: expert, isLoading, isError, refetch } = useQuery({
    queryKey: ['experts', decodedName],
    queryFn: () => expertsApi.get(encodedName),
    enabled: !!decodedName,
  })

  const { data: costLimits, isError: isCostLimitsError } = useQuery({
    queryKey: ['cost', 'limits'],
    queryFn: costApi.getLimits,
    enabled: activeTab === 'chat',
  })
  const chatMaxBudget = costLimits?.expert_chat_max ?? 0
  const chatControlsLocked = socketSessionActive || isStreaming

  useEffect(() => {
    if (chatControlsLocked || chatMaxBudget <= 0) return
    setChatBudgetInput(current => clampBrowserExpertChatBudgetInput(current, chatMaxBudget))
  }, [chatControlsLocked, chatMaxBudget])

  const { data: gaps, isLoading: isGapsLoading, isError: isGapsError, isFetching: isGapsFetching, refetch: refetchGaps } = useQuery({
    queryKey: ['experts', decodedName, 'gaps'],
    queryFn: () => expertsApi.getGaps(encodedName),
    enabled: !!decodedName && activeTab === 'gaps',
  })

  const { data: claims, isLoading: isClaimsLoading, isError: isClaimsError, isFetching: isClaimsFetching, refetch: refetchClaims } = useQuery({
    queryKey: ['experts', decodedName, 'claims'],
    queryFn: () => expertsApi.getClaims(encodedName),
    enabled: !!decodedName && activeTab === 'claims',
  })

  const { data: decisions, isLoading: isDecisionsLoading, isError: isDecisionsError, isFetching: isDecisionsFetching, refetch: refetchDecisions } = useQuery({
    queryKey: ['experts', decodedName, 'decisions'],
    queryFn: () => expertsApi.getDecisions(encodedName),
    enabled: !!decodedName && activeTab === 'decisions',
  })

  const { data: history, isLoading: isHistoryLoading, isError: isHistoryError, isFetching: isHistoryFetching, refetch: refetchHistory } = useQuery({
    queryKey: ['experts', decodedName, 'history'],
    queryFn: () => expertsApi.getHistory(encodedName),
    enabled: !!decodedName && activeTab === 'history',
  })

  const { data: skillsData, isLoading: isSkillsLoading, isError: isSkillsError, isFetching: isSkillsFetching, refetch: refetchSkills } = useQuery({
    queryKey: ['experts', decodedName, 'skills'],
    queryFn: () => expertsApi.getSkills(encodedName),
    enabled: !!decodedName && activeTab === 'skills',
  })

  const { data: conversations, isError: isConversationsError, isFetching: isConversationsFetching, refetch: refetchConversations } = useQuery({
    queryKey: ['experts', decodedName, 'conversations'],
    queryFn: () => expertsApi.listConversations(encodedName),
    enabled: !!decodedName && activeTab === 'chat',
  })

  const deleteConversationMutation = useMutation({
    mutationFn: (sid: string) => expertsApi.deleteConversation(encodedName, sid),
    onSuccess: () => { refetchConversations(); toast.success('Conversation deleted') },
    onError: () => toast.error('Failed to delete conversation'),
  })

  const loadConversation = useCallback(async (sid: string) => {
    try {
      wsClient.endChat()
      setSocketSessionActive(false)
      setMeteredChatConfirmed(false)
      const data = await expertsApi.getConversation(encodedName, sid)
      setSessionId(data.session_id)
      setChatMessages(
        data.messages
          .filter((m: { role: string }) => m.role === 'user' || m.role === 'assistant')
          .map((m: { role: string; content: string }) => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
            timestamp: new Date().toISOString(),
          }))
      )
    } catch {
      toast.error('Failed to load conversation')
    }
  }, [encodedName])

  const startNewChat = useCallback(() => {
    wsClient.endChat()
    setChatMessages([])
    setSessionId(null)
    setChatInput('')
    setIsStreaming(false)
    setIsStopping(false)
    setStreamingContent('')
    streamingContentRef.current = ''
    setActiveTools([])
    setSocketSessionActive(false)
    setMeteredChatConfirmed(false)
  }, [])

  const installSkillMutation = useMutation({
    mutationFn: (skillName: string) => expertsApi.installSkill(encodedName, skillName),
    onSuccess: () => { refetchSkills(); toast.success('Skill installed') },
    onError: () => toast.error('Failed to install skill'),
  })

  const removeSkillMutation = useMutation({
    mutationFn: (skillName: string) => expertsApi.removeSkill(encodedName, skillName),
    onSuccess: () => { refetchSkills(); toast.success('Skill removed') },
    onError: () => toast.error('Failed to remove skill'),
  })

  const portraitMutation = useMutation({
    mutationFn: (options?: { force?: boolean }) => expertsApi.generatePortrait(encodedName, options),
    onSuccess: () => {
      refetch()
      toast.success('Portrait generated!')
    },
    onError: () => toast.error('Failed to generate portrait'),
  })

  const handlePortraitClick = useCallback(() => {
    if (expert?.portrait_url) {
      const confirmed = window.confirm('Replace the existing portrait? Use this only when you intentionally want a new image.')
      if (!confirmed) return
      portraitMutation.mutate({ force: true })
      return
    }
    portraitMutation.mutate(undefined)
  }, [expert?.portrait_url, portraitMutation])

  // REST fallback mutation (used when WebSocket is disconnected)
  const chatMutation = useMutation({
    mutationFn: (chatRequest: BrowserExpertChatRequestPayload) => (
      expertsApi.chat(encodedName, chatRequest, sessionId ?? undefined)
    ),
    onSuccess: (data) => {
      if (data.session_id) setSessionId(data.session_id)
      setChatMessages(prev => [...prev, data])
      setMeteredChatConfirmed(false)
    },
    onError: () => {
      setSessionId(null)
      setMeteredChatConfirmed(false)
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: browserExpertChatFailureMessage({
          error: 'Expert chat failed. Start a new session and retry.',
          retryable: true,
        }),
        timestamp: new Date().toISOString(),
        error: true,
      }])
      toast.error('Failed to get response from expert')
    },
  })

  const prepareChatRequest = useCallback((message: string) => {
    const result = prepareBrowserExpertChatRequest({
      message,
      chatMode,
      budgetInput: chatBudgetInput,
      maxBudget: chatMaxBudget,
      meteredConfirmed: meteredChatConfirmed,
    })
    if (!result.ok) {
      toast.error(result.error)
      return null
    }
    return result.request
  }, [chatBudgetInput, chatMaxBudget, chatMode, meteredChatConfirmed])

  const handleSendMessage = useCallback((e?: React.FormEvent) => {
    e?.preventDefault()
    if (!chatInput.trim() || isStreaming || chatMutation.isPending) return
    const message = chatInput.trim()

    // Detect slash commands
    if (message.startsWith('/')) {
      if (message === '/new') {
        startNewChat()
        setThoughts([])
        toast.success('New conversation')
        return
      }
      if (message === '/clear' && (!wsClient.connected || !socketSessionActive)) {
        setChatMessages([])
        setThoughts([])
        setChatInput('')
        setShowSlashMenu(false)
        toast.success('Cleared')
        return
      }
      // Send command via WebSocket
      if (wsClient.connected) {
        setChatInput('')
        setShowSlashMenu(false)
        wsClient.sendCommand(message)
        return
      }
      toast.error('Commands require a WebSocket connection')
      return
    }

    const chatRequest = prepareChatRequest(message)
    if (!chatRequest) return
    setChatInput('')
    setShowSlashMenu(false)

    setChatMessages(prev => [...prev, { role: 'user', content: message, timestamp: new Date().toISOString() }])

    // Try WebSocket streaming first, fall back to REST
    if (wsClient.connected) {
      setIsStreaming(true)
      setIsStopping(false)
      setStreamingContent('')
      streamingContentRef.current = ''
      setActiveTools([])
      setThoughts([])
      userScrolledRef.current = false
      wsClient.startChat(decodedName, chatRequest, sessionId ?? undefined)
    } else {
      chatMutation.mutate(chatRequest)
    }
  }, [
    chatInput,
    isStreaming,
    chatMutation,
    decodedName,
    sessionId,
    prepareChatRequest,
    socketSessionActive,
    startNewChat,
  ])

  const handleStopStreaming = useCallback(() => {
    if (isStopping) return
    if (!wsClient.stopChat()) {
      setIsStreaming(false)
      setIsStopping(false)
      setStreamingContent('')
      streamingContentRef.current = ''
      setActiveTools([])
      toast.error('Cannot stop chat because the WebSocket connection is unavailable.')
      return
    }
    setIsStopping(true)
  }, [isStopping])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }, [handleSendMessage])

  const handleRetry = useCallback((index: number) => {
    // Find the preceding user message and re-send
    const userMsg = chatMessages.slice(0, index).reverse().find(m => m.role === 'user')
    if (!userMsg) return
    const chatRequest = prepareChatRequest(userMsg.content)
    if (!chatRequest) return
    setChatMessages(prev => prev.slice(0, index))
    if (wsClient.connected) {
      setIsStreaming(true)
      setIsStopping(false)
      setStreamingContent('')
      streamingContentRef.current = ''
      setActiveTools([])
      wsClient.startChat(decodedName, chatRequest, sessionId ?? undefined)
    } else {
      chatMutation.mutate(chatRequest)
    }
  }, [chatMessages, decodedName, sessionId, chatMutation, prepareChatRequest])

  const handleEdit = useCallback((index: number, content: string) => {
    setChatMessages(prev => prev.slice(0, index))
    setChatInput(content)
  }, [])

  useEffect(() => {
    if (!userScrolledRef.current) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatMessages, streamingContent])

  const numericChatBudget = Number(chatBudgetInput)
  const chatBudgetValid = (
    meteredChatConfirmed
    && Number.isFinite(numericChatBudget)
    && numericChatBudget > 0
    && chatMaxBudget > 0
    && numericChatBudget <= chatMaxBudget
  )
  if (isLoading) return <DetailSkeleton />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <AlertTriangle className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Unable to load expert</p>
        <p className="text-sm text-muted-foreground mb-4">Could not connect to the backend. Expert data will appear here once the server is running.</p>
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
    { key: 'skills', label: 'Skills' },
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
          <div className="relative group/avatar flex-shrink-0">
            <ExpertPortrait
              name={expert.name}
              portraitUrl={expert.portrait_url}
              className="w-12 h-12 rounded-lg"
              iconClassName="w-6 h-6"
            />
            <button
              onClick={handlePortraitClick}
              disabled={portraitMutation.isPending}
              className="absolute inset-0 rounded-lg bg-black/50 flex items-center justify-center opacity-0 group-hover/avatar:opacity-100 transition-opacity"
              title={expert.portrait_url ? 'Replace portrait' : 'Generate portrait'}
            >
              {portraitMutation.isPending ? (
                <Loader2 className="w-4 h-4 text-white animate-spin" />
              ) : (
                <Camera className="w-4 h-4 text-white" />
              )}
            </button>
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
            <div className="flex flex-wrap gap-2 mt-2">
              <button
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary rounded text-xs font-medium hover:bg-primary/20 transition-colors"
                onClick={() => { setActiveTab('claims'); toast.info('Use CLI: deepr expert validate-citations "' + decodedName + '"') }}
              >
                <Shield className="w-3 h-3" />
                Validate Citations
              </button>
              <button
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary rounded text-xs font-medium hover:bg-primary/20 transition-colors"
                onClick={() => { setActiveTab('gaps'); toast.info('Use CLI: deepr expert discover-gaps "' + decodedName + '"') }}
              >
                <Sparkles className="w-3 h-3" />
                Discover Gaps
              </button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-secondary rounded-lg w-fit overflow-x-auto">
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
          <div className="flex h-full">
            {/* Conversation sidebar */}
            {conversations && conversations.length > 0 && (
              <div className="hidden md:flex w-56 border-r flex-shrink-0 flex-col overflow-hidden">
                <div className="p-3 border-b">
                  <Button size="sm" className="w-full" variant="outline" onClick={startNewChat}>
                    New Chat
                  </Button>
                </div>
                <div className="flex-1 overflow-auto">
                  {conversations.map((conv) => (
                    <div
                      key={conv.session_id}
                      className={cn(
                        'px-3 py-2 border-b cursor-pointer hover:bg-muted/50 transition-colors group/conv',
                        sessionId === conv.session_id && 'bg-muted',
                      )}
                      onClick={() => loadConversation(conv.session_id)}
                    >
                      <p className="text-xs text-foreground truncate">{conv.preview || 'Empty conversation'}</p>
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-[10px] text-muted-foreground">
                          {conv.message_count} msgs{conv.cost > 0 ? ` · ${formatCurrency(conv.cost)}` : ''}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            if (window.confirm(`Delete this conversation (${conv.message_count} messages)? This cannot be undone.`)) {
                              deleteConversationMutation.mutate(conv.session_id)
                            }
                          }}
                          className="text-[10px] text-destructive opacity-0 group-hover/conv:opacity-100 transition-opacity"
                          aria-label="Delete conversation"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* Chat area */}
            <div className="flex-1 flex flex-col min-w-0">
            {isConversationsError && (
              <div className="p-4 pb-0">
                <PartialQueryError
                  title={conversations ? 'Conversation history refresh failed' : 'Conversation history unavailable'}
                  description={conversations
                    ? 'Previously loaded conversations remain visible, but may be out of date.'
                    : 'You can keep chatting, but saved conversations could not be loaded.'}
                  onRetry={() => void refetchConversations()}
                  retrying={isConversationsFetching}
                />
              </div>
            )}
            {/* Messages */}
            <div
              className="flex-1 overflow-auto p-6 space-y-4"
              role="log"
              aria-live="polite"
              aria-relevant="additions"
              onScroll={(e) => {
                const el = e.currentTarget
                const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
                userScrolledRef.current = !atBottom
              }}
            >
              {chatMessages.length === 0 && !isStreaming && (
                <div className="flex flex-col items-center justify-center text-center py-12">
                  <ExpertPortrait
                    name={expert.name}
                    portraitUrl={expert.portrait_url}
                    className="w-16 h-16 rounded-full mb-3 ring-2 ring-muted"
                    iconClassName="w-6 h-6 text-muted-foreground"
                    FallbackIcon={MessageSquare}
                    fallbackClassName="bg-muted"
                  />
                  <h3 className="text-sm font-medium text-foreground mb-1">Start a conversation</h3>
                  <p className="text-xs text-muted-foreground max-w-xs">
                    Ask {expert.name} questions about their domain expertise.
                  </p>
                </div>
              )}
              {chatMessages.map((msg, index) => (
                <div key={msg.id || index}>
                  <div className={cn('flex gap-3 group', msg.role === 'user' && 'justify-end')}>
                    <div className={cn(
                      'max-w-[70%] rounded-lg p-3 text-sm relative',
                      msg.error
                        ? 'bg-destructive/10 text-foreground border border-destructive/30'
                        : msg.role === 'user'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-secondary text-foreground'
                    )}>
                      {/* Tool call blocks for completed messages */}
                      {msg.tool_calls && msg.tool_calls.length > 0 && (
                        <div className="mb-2 space-y-1">
                          {msg.tool_calls.map((tc, i) => (
                            <ToolCallBlock key={i} tool={tc.tool} query={tc.query} />
                          ))}
                        </div>
                      )}
                      {msg.role === 'assistant' ? (
                        <MarkdownMessage content={msg.content} />
                      ) : (
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                      )}
                      {/* Confidence indicator */}
                      {msg.role === 'assistant' && msg.confidence != null && msg.confidence < 0.5 && (
                        <div className="flex items-center gap-1.5 mt-2 text-xs text-yellow-600 dark:text-yellow-500">
                          <AlertTriangle className="w-3 h-3" />
                          <span>Low confidence - consider verifying</span>
                        </div>
                      )}
                      <div className={cn(
                        'flex items-center gap-2 text-[10px] mt-1',
                        msg.role === 'user' ? (msg.error ? 'text-destructive' : 'text-primary-foreground/60') : 'text-muted-foreground'
                      )}>
                        <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                        {msg.error && <span>{msg.role === 'assistant' ? 'Response failed' : 'Failed to send'}</span>}
                        {msg.cost != null && msg.cost > 0 && <span>${msg.cost.toFixed(4)}</span>}
                        <MessageActions
                          content={msg.content}
                          role={msg.role}
                          index={index}
                          onRetry={handleRetry}
                          onEdit={handleEdit}
                        />
                      </div>
                    </div>
                  </div>
                  {/* Follow-up suggestion chips */}
                  {msg.follow_ups && msg.follow_ups.length > 0 && index === chatMessages.length - 1 && (
                    <div className="flex flex-wrap gap-2 mt-2 ml-0">
                      {msg.follow_ups.map((fu, i) => (
                        <button
                          key={i}
                          onClick={() => {
                            const chatRequest = prepareChatRequest(fu)
                            if (!chatRequest) return
                            setChatMessages(prev => [...prev, { role: 'user', content: fu, timestamp: new Date().toISOString() }])
                            if (wsClient.connected) {
                              setIsStreaming(true)
                              setIsStopping(false)
                              setStreamingContent('')
                              streamingContentRef.current = ''
                              setActiveTools([])
                              wsClient.startChat(decodedName, chatRequest, sessionId ?? undefined)
                            } else {
                              chatMutation.mutate(chatRequest)
                            }
                            setChatInput('')
                          }}
                          className="px-3 py-1.5 rounded-full border text-xs text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
                        >
                          {fu}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {/* Active tool indicators during streaming */}
              {activeTools.map((t) => (
                <ToolCallBlock key={`${t.tool}-${t.startedAt}`} tool={t.tool} query={t.query} running />
              ))}
              {/* Thinking panel */}
              {thoughts.length > 0 && (
                <ThinkingPanel thoughts={thoughts} isStreaming={isStreaming} />
              )}
              {/* Confirm dialog */}
              {confirmRequest && (
                <ConfirmDialog
                  request={confirmRequest}
                  onApprove={() => {
                    wsClient.sendConfirmResponse(confirmRequest.request_id, true)
                    setConfirmRequest(null)
                  }}
                  onDeny={() => {
                    wsClient.sendConfirmResponse(confirmRequest.request_id, false)
                    setConfirmRequest(null)
                  }}
                />
              )}
              {/* Plan display */}
              {planSteps.length > 0 && (
                <PlanDisplay query={planQuery} steps={planSteps} />
              )}
              {/* Streaming bubble */}
              {isStreaming && (
                <div className="flex gap-3" role="status">
                  <div className="max-w-[70%] rounded-lg p-3 text-sm bg-secondary text-foreground">
                    {streamingContent ? (
                      <>
                        <MarkdownMessage content={streamingContent} />
                        <span className="inline-block w-2 h-4 bg-foreground/60 animate-pulse ml-0.5 align-text-bottom" />
                      </>
                    ) : (
                      <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    )}
                  </div>
                </div>
              )}
              {/* REST fallback loading */}
              {chatMutation.isPending && !isStreaming && (
                <div className="flex gap-3">
                  <div className="bg-secondary rounded-lg p-3">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Compact banner */}
            {compactSuggest && (
              <div className="px-4 pt-2">
                <CompactBanner
                  messageCount={compactSuggest.messageCount}
                  onCompact={() => { wsClient.sendCompact(); setCompactSuggest(null) }}
                  onDismiss={() => setCompactSuggest(null)}
                />
              </div>
            )}

            <div className="px-4 pt-3 border-t bg-muted/20 space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <label className="flex items-center gap-2">
                  <span className="font-medium text-foreground">Session ceiling</span>
                  <span className="flex items-center rounded-md border bg-background px-2 py-1">
                    <span className="text-muted-foreground">$</span>
                    <input
                      type="number"
                      min="0.01"
                      max={chatMaxBudget || undefined}
                      step="0.01"
                      value={chatBudgetInput}
                      disabled={chatControlsLocked}
                      onChange={(event) => setChatBudgetInput(event.target.value)}
                      className="w-20 bg-transparent pl-1 outline-none disabled:cursor-not-allowed"
                      aria-label="Expert chat session budget"
                    />
                  </span>
                </label>
                <span className="text-muted-foreground">
                  {chatMaxBudget > 0
                    ? `Server maximum: $${chatMaxBudget.toFixed(2)}`
                    : 'Server budget controls unavailable'}
                </span>
                {socketSessionActive && (
                  <span className="text-muted-foreground">Locked for the active session</span>
                )}
              </div>
              <label className="flex items-start gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={meteredChatConfirmed}
                  disabled={chatControlsLocked}
                  onChange={(event) => setMeteredChatConfirmed(event.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  I approve metered API chat up to this session ceiling. Browser chat currently
                  supports API capacity only; use CLI or MCP for local and plan capacity.
                </span>
              </label>
              {isCostLimitsError && (
                <p className="text-xs text-destructive">
                  Cost limits could not be loaded, so metered browser chat is disabled.
                </p>
              )}
            </div>

            {/* Input */}
            <form onSubmit={handleSendMessage} className="p-4 pt-3 flex gap-2 items-end relative">
              {/* Mode badge */}
              <span className={cn(
                'absolute -top-5 left-4 px-2 py-0.5 rounded text-[10px] font-semibold text-white',
                CHAT_MODES.find(m => m.value === chatMode)?.color || 'bg-cyan-500'
              )}>
                {chatMode}
              </span>

              {/* Slash command autocomplete */}
              <div className="flex-1 relative">
                <SlashCommandMenu
                  inputValue={chatInput}
                  visible={showSlashMenu}
                  onSelect={(cmd) => { setChatInput(cmd); setShowSlashMenu(false) }}
                  onClose={() => setShowSlashMenu(false)}
                />
                <Textarea
                  value={chatInput}
                  onChange={(e) => {
                    setChatInput(e.target.value)
                    setShowSlashMenu(/^\/\w*$/.test(e.target.value))
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={`Ask ${expert.name} a question... (/ for commands)`}
                  className="min-h-[40px] max-h-[200px]"
                  autoGrow
                  rows={1}
                />
              </div>
              {isStreaming ? (
                <Button
                  type="button"
                  size="icon"
                  variant="destructive"
                  onClick={handleStopStreaming}
                  disabled={isStopping}
                  aria-label={isStopping ? 'Stopping chat' : 'Stop streaming'}
                >
                  {isStopping ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="icon"
                  disabled={
                    !chatInput.trim()
                    || (!chatInput.trim().startsWith('/') && !chatBudgetValid)
                  }
                  loading={chatMutation.isPending}
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </Button>
              )}
            </form>
            </div>{/* end chat area */}
          </div>
        )}

        {activeTab === 'claims' && (
          <div className="p-6 space-y-3">
            {isClaimsError && claims && (
              <PartialQueryError
                title="Claims refresh failed"
                description="Previously loaded claims remain visible, but may be out of date."
                onRetry={() => void refetchClaims()}
                retrying={isClaimsFetching}
              />
            )}
            {isClaimsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : isClaimsError && !claims ? (
              <PartialQueryError
                title="Claims unavailable"
                description="The expert loaded, but its claims could not be retrieved."
                onRetry={() => void refetchClaims()}
                retrying={isClaimsFetching}
              />
            ) : !sortedClaims.length ? (
              <EmptyState icon={Lightbulb} title="No claims yet" description="Claims will appear here as the expert forms beliefs from evidence." />
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
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-secondary text-xs font-medium text-foreground">
                              {claim.sources.length}
                            </span>
                            {claim.sources.map((src) => src.support_class && (
                              <SupportClassBadge key={src.id} support={src.support_class} />
                            ))}
                          </div>
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
            {isGapsError && gaps && (
              <PartialQueryError
                title="Knowledge gaps refresh failed"
                description="Previously loaded knowledge gaps remain visible, but may be out of date."
                onRetry={() => void refetchGaps()}
                retrying={isGapsFetching}
              />
            )}
            {isGapsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : isGapsError && !gaps ? (
              <PartialQueryError
                title="Knowledge gaps unavailable"
                description="The expert loaded, but its knowledge gaps could not be retrieved."
                onRetry={() => void refetchGaps()}
                retrying={isGapsFetching}
              />
            ) : !gaps || gaps.length === 0 ? (
              <EmptyState icon={SearchX} title="No knowledge gaps" description="Knowledge gaps will appear here as the expert identifies areas needing more research." />
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
            {isDecisionsError && decisions && (
              <PartialQueryError
                title="Decisions refresh failed"
                description="Previously loaded decisions remain visible, but may be out of date."
                onRetry={() => void refetchDecisions()}
                retrying={isDecisionsFetching}
              />
            )}
            {isDecisionsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : isDecisionsError && !decisions ? (
              <PartialQueryError
                title="Decisions unavailable"
                description="The expert loaded, but its decision records could not be retrieved."
                onRetry={() => void refetchDecisions()}
                retrying={isDecisionsFetching}
              />
            ) : !sortedDecisions.length ? (
              <EmptyState icon={GitBranch} title="No decisions yet" description="Decision records will appear here as the expert makes research decisions." />
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
            {isHistoryError && history && (
              <PartialQueryError
                title="Activity history refresh failed"
                description="Previously loaded activity remains visible, but may be out of date."
                onRetry={() => void refetchHistory()}
                retrying={isHistoryFetching}
              />
            )}
            {isHistoryLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : isHistoryError && !history ? (
              <PartialQueryError
                title="Activity history unavailable"
                description="The expert loaded, but its learning history could not be retrieved."
                onRetry={() => void refetchHistory()}
                retrying={isHistoryFetching}
              />
            ) : !history || history.length === 0 ? (
              <EmptyState icon={Clock} title="No activity yet" description="Learning events and research activity will be logged here." />
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

        {activeTab === 'skills' && (
          <div className="p-6 space-y-6">
            {isSkillsError && skillsData && (
              <PartialQueryError
                title="Skills refresh failed"
                description="Previously loaded skills remain visible, but may be out of date."
                onRetry={() => void refetchSkills()}
                retrying={isSkillsFetching}
              />
            )}
            {isSkillsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : isSkillsError && !skillsData ? (
              <PartialQueryError
                title="Skills unavailable"
                description="Installed and available skills could not be retrieved for this expert."
                onRetry={() => void refetchSkills()}
                retrying={isSkillsFetching}
              />
            ) : (
              <>
            {/* Installed Skills */}
            <div>
              <h3 className="text-sm font-semibold text-foreground mb-3">Installed Skills</h3>
              {!skillsData?.installed_skills?.length ? (
                <div className="flex flex-col items-center justify-center text-center py-8">
                  <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mb-2">
                    <Sparkles className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <p className="text-xs text-muted-foreground">No skills installed yet. Install one below to extend this expert.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {skillsData.installed_skills.map((skill: Skill) => (
                    <SkillCard
                      key={skill.name}
                      skill={skill}
                      installed
                      action={
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            if (window.confirm(`Remove the '${skill.name}' skill from this expert?`)) {
                              removeSkillMutation.mutate(skill.name)
                            }
                          }}
                          disabled={removeSkillMutation.isPending}
                        >
                          Remove
                        </Button>
                      }
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Available Skills */}
            {skillsData?.available_skills && skillsData.available_skills.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-3">Available Skills</h3>
                <div className="space-y-2">
                  {skillsData.available_skills.map((skill: Skill) => (
                    <SkillCard
                      key={skill.name}
                      skill={skill}
                      action={
                        <Button size="sm" onClick={() => installSkillMutation.mutate(skill.name)} disabled={installSkillMutation.isPending}>
                          Install
                        </Button>
                      }
                    />
                  ))}
                </div>
              </div>
            )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
