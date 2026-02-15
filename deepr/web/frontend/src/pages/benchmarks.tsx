import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { benchmarksApi } from '@/api/benchmarks'
import { configApi } from '@/api/config'
import { cn, formatCurrency } from '@/lib/utils'
import { CHART_THEME } from '@/lib/chart-theme'
import { toast } from 'sonner'
import {
  Play,
  Trophy,
  Clock,
  Zap,
  DollarSign,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Gauge,
  Shield,
  TrendingUp,
  Box,
  Cpu,
  Key,
  KeyRound,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
} from 'recharts'
import type { BenchmarkRanking, BenchmarkFile, RegistryModel } from '@/types'

// Muted palette for model comparison bars
const MODEL_COLORS = [
  'hsl(215, 50%, 55%)',
  'hsl(175, 40%, 48%)',
  'hsl(255, 35%, 58%)',
  'hsl(30, 45%, 52%)',
  'hsl(340, 35%, 55%)',
  'hsl(195, 45%, 50%)',
  'hsl(140, 35%, 48%)',
  'hsl(60, 30%, 48%)',
  'hsl(280, 30%, 52%)',
  'hsl(10, 40%, 52%)',
  'hsl(220, 30%, 60%)',
  'hsl(160, 30%, 52%)',
]

type Tier = 'all' | 'chat' | 'news' | 'research' | 'docs'
const TIER_PRIORITY: Record<string, number> = { research: 0, docs: 1, news: 2, chat: 3 }
const TIER_ORDER: Tier[] = ['research', 'docs', 'news', 'chat']
const TIER_LABELS: Record<string, string> = { research: 'Deep Research', docs: 'Docs', news: 'News', chat: 'Chat', all: 'All' }

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  gemini: 'Google',
  xai: 'xAI',
  anthropic: 'Anthropic',
  'azure-foundry': 'Azure',
}
function providerLabel(id: string): string {
  return PROVIDER_LABELS[id] ?? id
}

function inferTier(reg: RegistryModel): string {
  if (reg.specializations.includes('research')) return 'research'
  if (reg.specializations.includes('documentation')) return 'docs'
  if (reg.specializations.includes('news')) return 'news'
  return 'chat'
}

function formatContext(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 === 0 ? 0 : 1)}M`
  return `${(tokens / 1_000).toFixed(0)}K`
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60_000)}m`
}

export default function Benchmarks() {
  const queryClient = useQueryClient()
  const [selectedTier, setSelectedTier] = useState<Tier>('research')
  const [expandedModel, setExpandedModel] = useState<string | null>(null)
  const [showRunPanel, setShowRunPanel] = useState(false)
  const [runOpts, setRunOpts] = useState({ tier: 'all' as Tier, quick: false, no_judge: false })
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [showAvailableOnly, setShowAvailableOnly] = useState(true)
  const [routingMode, setRoutingMode] = useState<'best' | 'balanced' | 'value'>('balanced')
  const [estimateData, setEstimateData] = useState<{
    estimated_cost: number
    model_count: number
    provider_count: number
    tier: string
  } | null>(null)

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
  })
  const providerKeys = config?.provider_keys ?? {}

  const { data: fileList } = useQuery({
    queryKey: ['benchmarks', 'list'],
    queryFn: benchmarksApi.list,
  })

  const { data: latestData, isLoading: benchLoading, isError: benchError } = useQuery({
    queryKey: ['benchmarks', selectedFile ? 'file' : 'latest', selectedFile],
    queryFn: () => selectedFile ? benchmarksApi.get(selectedFile) : benchmarksApi.getLatest(),
  })

  const { data: registry, isLoading: regLoading, isError: regError } = useQuery({
    queryKey: ['models', 'registry'],
    queryFn: benchmarksApi.getRegistry,
  })

  const { data: routing } = useQuery({
    queryKey: ['benchmarks', 'routing'],
    queryFn: benchmarksApi.getRouting,
  })

  const { data: benchStatus } = useQuery({
    queryKey: ['benchmarks', 'status'],
    queryFn: benchmarksApi.getStatus,
    refetchInterval: (query) => {
      return query.state.data?.status === 'running' ? 3000 : false
    },
  })

  const startMutation = useMutation({
    mutationFn: benchmarksApi.start,
    onSuccess: () => {
      toast.success('Benchmark started')
      setShowRunPanel(false)
      setEstimateData(null)
      queryClient.invalidateQueries({ queryKey: ['benchmarks', 'status'] })
    },
    onError: (err: Error) => toast.error(err.message || 'Failed to start benchmark'),
  })

  const estimateMutation = useMutation({
    mutationFn: benchmarksApi.estimate,
    onSuccess: (data) => setEstimateData(data),
    onError: (err: Error) => toast.error(err.message || 'Failed to estimate cost'),
  })

  const result = latestData?.result
  const rankings = result?.rankings ?? []
  const results = result?.results ?? []

  // Build registry lookup
  const registryMap = useMemo(() => {
    const map: Record<string, RegistryModel> = {}
    for (const m of registry ?? []) map[m.model_key] = m
    return map
  }, [registry])

  // Set of benchmarked model keys (with evals)
  const benchmarkedKeys = useMemo(
    () => new Set(rankings.filter((r) => r.num_evals > 0).map((r) => r.model_key)),
    [rankings]
  )

  // Unbenchmarked registry models, grouped by inferred tier
  const unbenchmarked = useMemo(() => {
    if (!registry) return []
    return registry
      .filter((m) => !benchmarkedKeys.has(m.model_key))
      .filter((m) => !m.model_key.startsWith('azure-foundry/')) // skip azure dupes
      .map((m) => ({ ...m, tier: inferTier(m) }))
  }, [registry, benchmarkedKeys])

  // Filter benchmarked by tier
  const filtered = selectedTier === 'all'
    ? rankings
    : rankings.filter((r) => r.tier === selectedTier)

  // Sort: group by tier priority then quality desc
  const sorted = useMemo(
    () => [...filtered].filter((r) => r.num_evals > 0).sort((a, b) => {
      if (selectedTier === 'all') {
        const tierDiff = (TIER_PRIORITY[a.tier] ?? 9) - (TIER_PRIORITY[b.tier] ?? 9)
        if (tierDiff !== 0) return tierDiff
      }
      return b.avg_quality - a.avg_quality
    }),
    [filtered, selectedTier]
  )

  // Top model per tier for hero cards — mode-aware selection
  // Best: highest quality regardless of cost (deep research default)
  // Balanced: best quality among cost-efficient models (within 10% of top quality, cheapest wins)
  // Value: lowest cost_per_quality with ≥50% quality floor
  const topByTier = useMemo(() => {
    const map: Record<string, BenchmarkRanking> = {}
    // Group by tier
    const byTier: Record<string, BenchmarkRanking[]> = {}
    for (const r of rankings) {
      if (r.num_evals === 0) continue
      byTier[r.tier] = byTier[r.tier] || []
      byTier[r.tier].push(r)
    }
    for (const [tier, models] of Object.entries(byTier)) {
      if (tier === 'research' || routingMode === 'best') {
        // Research always picks best quality (that's the point of deep research)
        // Best mode also picks by quality for all tiers
        map[tier] = models.reduce((a, b) => (b.avg_quality > a.avg_quality ? b : a))
      } else if (routingMode === 'value') {
        // Lowest cost_per_quality with quality ≥ 50%
        const viable = models.filter((m) => m.avg_quality >= 0.5)
        if (viable.length > 0) {
          map[tier] = viable.reduce((a, b) =>
            (b.cost_per_quality || Infinity) < (a.cost_per_quality || Infinity) ? b : a
          )
        }
      } else {
        // Balanced: within 10% of top quality, then cheapest
        const topQuality = Math.max(...models.map((m) => m.avg_quality))
        const threshold = topQuality * 0.9
        const nearTop = models.filter((m) => m.avg_quality >= threshold)
        map[tier] = nearTop.reduce((a, b) =>
          (b.cost_per_quality || Infinity) < (a.cost_per_quality || Infinity) ? b : a
        )
      }
    }
    return map
  }, [rankings, routingMode])

  // Tiers with data
  const tiers = useMemo(() => {
    const benchTiers = new Set(rankings.map((r) => r.tier))
    const regTiers = new Set(unbenchmarked.map((m) => m.tier))
    const all = new Set([...benchTiers, ...regTiers])
    return ['all', ...TIER_ORDER.filter((t) => all.has(t))]
  }, [rankings, unbenchmarked])

  // Unbenchmarked models for current tier
  const tierUnbenchmarked = useMemo(() => {
    if (selectedTier === 'all') return unbenchmarked
    return unbenchmarked.filter((m) => m.tier === selectedTier)
  }, [unbenchmarked, selectedTier])

  // Filter by provider availability
  const availableSorted = useMemo(
    () => showAvailableOnly
      ? sorted.filter((r) => providerKeys[r.model_key.split('/')[0]] !== false)
      : sorted,
    [sorted, showAvailableOnly, providerKeys]
  )

  const availableUnbenchmarked = useMemo(
    () => showAvailableOnly
      ? tierUnbenchmarked.filter((m) => providerKeys[m.provider] !== false)
      : tierUnbenchmarked,
    [tierUnbenchmarked, showAvailableOnly, providerKeys]
  )

  const isRunning = benchStatus?.status === 'running'
  const isLoading = benchLoading || regLoading
  const totalModels = (registry?.length ?? 0) - (registry?.filter(m => m.model_key.startsWith('azure-foundry/')).length ?? 0)

  // Compute average report length per tier from results
  // NOTE: must be before early returns to satisfy Rules of Hooks

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (regError && benchError && !registry && !result) {
    return (
      <div className="p-6 space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Models</h1>
          <p className="text-sm text-muted-foreground mt-1">Model registry and benchmark results</p>
        </div>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertCircle className="w-10 h-10 text-muted-foreground/40 mb-3" />
          <p className="text-lg font-medium text-foreground mb-1">Unable to load models</p>
          <p className="text-sm text-muted-foreground mb-4">
            Could not connect to the backend. Model data and benchmarks will appear here once the server is running.
          </p>
          <button
            onClick={() => queryClient.invalidateQueries()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Models</h1>
          <div className="flex items-center gap-3 mt-1">
            <p className="text-sm text-muted-foreground">
              {totalModels} models across {new Set(TIER_ORDER).size} tiers
              {result && <>{' \u00b7 '}{sorted.length} benchmarked{' \u00b7 '}{formatCurrency(result.total_cost)} eval cost</>}
            </p>
            {fileList && fileList.length > 1 && (
              <select
                value={selectedFile || latestData?.filename || ''}
                onChange={(e) => setSelectedFile(e.target.value || null)}
                className="text-xs border rounded px-2 py-1 bg-background text-foreground"
              >
                {fileList.map((f: BenchmarkFile) => (
                  <option key={f.filename} value={f.filename}>
                    {new Date(f.timestamp).toLocaleDateString()} {new Date(f.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ({f.model_count} models)
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRunning && (
            <span className="inline-flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/30 px-2.5 py-1 rounded-full">
              <Loader2 className="h-3 w-3 animate-spin" />
              Running
            </span>
          )}
          <button
            onClick={() => setShowRunPanel(!showRunPanel)}
            disabled={isRunning}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors border',
              'hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Play className="h-3 w-3" />
            Run Benchmark
          </button>
        </div>
      </div>

      {/* Run panel */}
      {showRunPanel && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex gap-1">
              {(['all', 'research', 'docs', 'news', 'chat'] as Tier[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setRunOpts({ ...runOpts, tier: t })}
                  className={cn(
                    'px-2.5 py-1 rounded text-xs font-medium transition-colors',
                    runOpts.tier === t ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground'
                  )}
                >
                  {TIER_LABELS[t] ?? t}
                </button>
              ))}
            </div>
            <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={runOpts.quick} onChange={() => setRunOpts({ ...runOpts, quick: !runOpts.quick })} className="rounded" />
              Quick
            </label>
            <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={runOpts.no_judge} onChange={() => setRunOpts({ ...runOpts, no_judge: !runOpts.no_judge })} className="rounded" />
              Skip judge
            </label>
            <button
              onClick={() => { setEstimateData(null); estimateMutation.mutate(runOpts) }}
              disabled={estimateMutation.isPending || startMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 ml-auto"
            >
              {estimateMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <DollarSign className="h-3 w-3" />}
              Estimate Cost
            </button>
          </div>
          {estimateData && (
            <div className="rounded-md border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-950/20 p-3 space-y-2">
              <div>
                <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                  Estimated cost: {formatCurrency(estimateData.estimated_cost)}
                </p>
                <p className="text-xs text-yellow-700 dark:text-yellow-300">
                  {estimateData.model_count} models from {estimateData.provider_count} providers ({estimateData.tier} tier)
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => { startMutation.mutate(runOpts); setEstimateData(null) }}
                  disabled={startMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {startMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                  Confirm & Start
                </button>
                <button
                  onClick={() => setEstimateData(null)}
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {isRunning && benchStatus?.output_lines && benchStatus.output_lines.length > 0 && (
            <pre className="text-xs text-muted-foreground bg-muted rounded p-2 max-h-24 overflow-y-auto font-mono">
              {benchStatus.output_lines.slice(-4).join('\n')}
            </pre>
          )}
        </div>
      )}

      {/* Status banners */}
      {benchStatus?.status === 'completed' && !showRunPanel && (
        <div className="rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 px-4 py-2.5 flex items-center gap-2 text-sm">
          <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
          <span className="text-green-800 dark:text-green-200">Benchmark completed</span>
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['benchmarks'] })}
            className="ml-auto text-xs text-green-700 dark:text-green-300 underline hover:no-underline"
          >
            Load new results
          </button>
        </div>
      )}
      {benchStatus?.status === 'failed' && (
        <div className="rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 px-4 py-2.5 flex items-center gap-2 text-sm">
          <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
          <span className="text-red-800 dark:text-red-200">Last benchmark failed (exit code {benchStatus.exit_code})</span>
        </div>
      )}

      {/* Routing mode toggle + Top picks per tier */}
      {Object.keys(topByTier).length > 0 && (
        <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">Recommended models by routing strategy</p>
          <div className="inline-flex rounded-lg border bg-muted p-0.5 text-xs">
            {(['best', 'balanced', 'value'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setRoutingMode(mode)}
                className={cn(
                  'px-3 py-1 rounded-md capitalize transition-colors',
                  routingMode === mode
                    ? 'bg-background text-foreground shadow-sm font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {mode === 'best' ? 'Best Quality' : mode === 'balanced' ? 'Balanced' : 'Cost Optimized'}
              </button>
            ))}
          </div>
        </div>
        <div className={cn("grid grid-cols-1 gap-4", TIER_ORDER.length <= 3 ? "md:grid-cols-3" : "md:grid-cols-4")}>
          {TIER_ORDER.map((tier) => {
            const top = topByTier[tier]
            if (!top) return (
              <div key={tier} className="rounded-lg border bg-card p-4 opacity-50">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Best {TIER_LABELS[tier] ?? tier}</div>
                <p className="text-sm text-muted-foreground">Not yet benchmarked</p>
              </div>
            )
            const modelName = top.model_key.split('/').pop() || top.model_key
            const provider = top.model_key.split('/')[0]
            return (
              <div key={tier} className="rounded-lg border bg-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Best {TIER_LABELS[tier] ?? tier}</span>
                  <Trophy className="h-3.5 w-3.5 text-yellow-500" />
                </div>
                <p className="text-lg font-semibold text-foreground">{modelName}</p>
                <p className="text-xs text-muted-foreground mb-3">{providerLabel(provider)}</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <p className="text-sm font-bold text-foreground">{(top.avg_quality * 100).toFixed(0)}%</p>
                    <p className="text-[10px] text-muted-foreground">Quality</p>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground">{formatLatency(top.avg_latency_ms)}</p>
                    <p className="text-[10px] text-muted-foreground">Speed</p>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground">{formatCurrency(top.total_cost)}</p>
                    <p className="text-[10px] text-muted-foreground">Cost</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        </div>
      )}

      {/* Tier filter tabs + available toggle */}
      <div className="flex items-center gap-2 border-b">
        <div className="flex gap-1 flex-1">
          {tiers.map((tier) => {
            const benchCount = tier === 'all'
              ? rankings.filter(r => r.num_evals > 0).length
              : rankings.filter(r => r.num_evals > 0 && r.tier === tier).length
            const unbenchCount = tier === 'all'
              ? unbenchmarked.length
              : unbenchmarked.filter(m => m.tier === tier).length
            const total = benchCount + unbenchCount
            return (
              <button
                key={tier}
                onClick={() => setSelectedTier(tier as Tier)}
                className={cn(
                  'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
                  selectedTier === tier
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )}
              >
                {tier === 'all' ? `All (${total})` : `${TIER_LABELS[tier] ?? tier} (${total})`}
              </button>
            )
          })}
        </div>
        <button
          onClick={() => setShowAvailableOnly(!showAvailableOnly)}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors border mb-px',
            showAvailableOnly
              ? 'bg-primary/10 text-primary border-primary/30'
              : 'text-muted-foreground hover:text-foreground border-transparent hover:border-border'
          )}
          title={showAvailableOnly ? 'Showing models with configured API keys' : 'Showing all models'}
        >
          {showAvailableOnly ? <Key className="h-3 w-3" /> : <KeyRound className="h-3 w-3" />}
          {showAvailableOnly ? 'Available' : 'All'}
        </button>
      </div>

      {/* Provider key status pills */}
      {Object.keys(providerKeys).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(providerKeys).map(([provider, hasKey]) => (
            <span
              key={provider}
              className={cn(
                'inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full',
                hasKey
                  ? 'bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400'
                  : 'bg-muted text-muted-foreground'
              )}
            >
              <span className={cn('h-1.5 w-1.5 rounded-full', hasKey ? 'bg-green-500' : 'bg-muted-foreground/40')} />
              {providerLabel(provider)}
            </span>
          ))}
        </div>
      )}

      {/* Quality chart — benchmarked models only */}
      {availableSorted.length > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <h3 className="text-sm font-medium text-foreground mb-4">Quality Ranking</h3>
          <div style={{ height: Math.max(220, availableSorted.length * 40) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={availableSorted.map((r, i) => ({
                model: `${(r.model_key.split('/').pop() || r.model_key)}${selectedTier === 'all' ? ` (${r.tier})` : ''}`,
                quality: r.avg_quality,
                fill: MODEL_COLORS[i % MODEL_COLORS.length],
              }))} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray={CHART_THEME.grid.strokeDasharray} stroke={CHART_THEME.grid.stroke} horizontal={false} />
                <XAxis
                  type="number"
                  domain={[0, 1]}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                  tick={{ fontSize: 11, fill: CHART_THEME.axis.tick }}
                  axisLine={{ stroke: CHART_THEME.axis.stroke }}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="model"
                  width={180}
                  tick={{ fontSize: 11, fill: CHART_THEME.axis.tick }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: CHART_THEME.tooltip.background,
                    border: `1px solid ${CHART_THEME.tooltip.border}`,
                    borderRadius: CHART_THEME.tooltip.borderRadius,
                    color: CHART_THEME.tooltip.text,
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [`${(value * 100).toFixed(1)}%`, 'Quality']}
                />
                <Bar dataKey="quality" radius={[0, 4, 4, 0]}>
                  {availableSorted.map((_, i) => (
                    <Cell key={i} fill={MODEL_COLORS[i % MODEL_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Benchmarked model cards */}
      {availableSorted.length > 0 && (
        <div className="space-y-2">
          {availableSorted.map((r, idx) => {
            const showTierHeader = selectedTier === 'all' && (idx === 0 || availableSorted[idx - 1].tier !== r.tier)
            const tierModels = availableSorted.filter((s) => s.tier === r.tier)
            const tierRank = tierModels.indexOf(r) + 1
            return (
              <div key={`${r.model_key}-${r.tier}`}>
                {showTierHeader && (
                  <div className={cn('flex items-center gap-2 pt-2', idx > 0 && 'mt-4 border-t pt-4')}>
                    <h3 className="text-sm font-semibold text-foreground">{TIER_LABELS[r.tier] ?? r.tier}</h3>
                    <span className="text-xs text-muted-foreground">({tierModels.length} benchmarked)</span>
                  </div>
                )}
                <ModelCard
                  ranking={r}
                  rank={tierRank}
                  registry={registryMap[r.model_key]}
                  isExpanded={expandedModel === `${r.model_key}-${r.tier}`}
                  onToggle={() => setExpandedModel(
                    expandedModel === `${r.model_key}-${r.tier}` ? null : `${r.model_key}-${r.tier}`
                  )}
                  results={results.filter((res) => res.model === r.model_key && (selectedTier === 'all' || res.tier === selectedTier))}
                />
              </div>
            )
          })}
        </div>
      )}

      {/* Unbenchmarked models from registry */}
      {availableUnbenchmarked.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 pt-2 border-t">
            <Box className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Available Models</h3>
            <span className="text-xs text-muted-foreground">({availableUnbenchmarked.length} not yet benchmarked)</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {availableUnbenchmarked
              .sort((a, b) => (TIER_PRIORITY[a.tier] ?? 9) - (TIER_PRIORITY[b.tier] ?? 9) || a.cost_per_query - b.cost_per_query)
              .map((m) => (
                <RegistryCard
                  key={m.model_key}
                  model={m}
                  isExpanded={expandedModel === `reg-${m.model_key}`}
                  onToggle={() => setExpandedModel(
                    expandedModel === `reg-${m.model_key}` ? null : `reg-${m.model_key}`
                  )}
                />
              ))}
          </div>
        </div>
      )}

      {/* Routing recommendations */}
      {routing && Object.keys(routing.task_preferences).length > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-medium text-foreground">Auto-Routing Recommendations</h3>
          </div>
          <p className="text-xs text-muted-foreground mb-4">
            Based on benchmark results. These override default routing when API keys are available.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {Object.entries(routing.task_preferences).map(([task, pref]) => (
              <div key={task} className="rounded-md border px-3 py-2.5">
                <p className="text-xs font-medium text-foreground capitalize mb-1.5">{task.replace(/_/g, ' ')}</p>
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Quality</span>
                  <span className="font-medium">{pref.best_quality.split('/').pop()}</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Value</span>
                  <span className="font-medium">{pref.best_value.split('/').pop()}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Card for a benchmarked model with quality scores */
function ModelCard({
  ranking,
  rank,
  registry,
  isExpanded,
  onToggle,
  results,
}: {
  ranking: BenchmarkRanking
  rank: number
  registry?: RegistryModel
  isExpanded: boolean
  onToggle: () => void
  results: Array<{ task_type: string; difficulty: string; quality: number; latency_ms: number; citation_count: number; error: string }>
}) {
  const modelName = ranking.model_key.split('/').pop() || ranking.model_key
  const provider = ranking.model_key.split('/')[0]
  const qualityPct = ranking.avg_quality * 100

  const taskEntries = useMemo(
    () => Object.entries(ranking.scores_by_type).sort(([, a], [, b]) => b - a),
    [ranking.scores_by_type]
  )

  const radarData = useMemo(() => {
    return Object.entries(ranking.scores_by_type).map(([task, score]) => ({
      task: task.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
      score: score,
      fullMark: 1,
    }))
  }, [ranking.scores_by_type])

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors text-left"
      >
        <span className={cn(
          'inline-flex items-center justify-center h-7 w-7 rounded-full text-xs font-bold shrink-0',
          rank === 1 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400' :
          rank === 2 ? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300' :
          rank === 3 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400' :
          'bg-muted text-muted-foreground'
        )}>
          {rank}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-foreground truncate">{modelName}</span>
            <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded bg-muted shrink-0">{providerLabel(provider)}</span>
            <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded bg-muted shrink-0">{TIER_LABELS[ranking.tier] ?? ranking.tier}</span>
            {registry && (
              <span className="text-[10px] text-muted-foreground shrink-0">{formatContext(registry.context_window)} ctx</span>
            )}
            {ranking.errors > 0 && (
              <span className="text-[10px] text-red-500 shrink-0">{ranking.errors} err</span>
            )}
          </div>
          {taskEntries.length > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
              {taskEntries.map(([task, score]) => (
                <span key={task} className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                  <span className="capitalize">{task.replace(/_/g, ' ')}</span>
                  <span className={cn(
                    'font-mono font-medium',
                    score >= 0.75 ? 'text-green-600 dark:text-green-400' :
                    score >= 0.5 ? 'text-yellow-600 dark:text-yellow-400' :
                    'text-red-600 dark:text-red-400'
                  )}>
                    {(score * 100).toFixed(0)}%
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="hidden sm:flex items-center gap-2 w-36 shrink-0">
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all', qualityPct >= 75 ? 'bg-green-500' : qualityPct >= 50 ? 'bg-yellow-500' : 'bg-red-500')}
              style={{ width: `${qualityPct}%` }}
            />
          </div>
          <span className="text-xs font-mono font-medium w-12 text-right">{qualityPct.toFixed(1)}%</span>
        </div>

        <div className="hidden md:flex items-center gap-4 shrink-0 text-xs text-muted-foreground">
          <span className="flex items-center gap-1" title="Latency">
            <Clock className="h-3 w-3" />
            {formatLatency(ranking.avg_latency_ms)}
          </span>
          <span className="flex items-center gap-1" title="Cost">
            <DollarSign className="h-3 w-3" />
            {formatCurrency(ranking.total_cost)}
          </span>
          <span className="flex items-center gap-1" title="Value (cost/quality)">
            <TrendingUp className="h-3 w-3" />
            {ranking.cost_per_quality < 100 ? formatCurrency(ranking.cost_per_quality) : '-'}/pt
          </span>
        </div>

        <ChevronDown className={cn('h-4 w-4 text-muted-foreground shrink-0 transition-transform', isExpanded && 'rotate-180')} />
      </button>

      {isExpanded && (
        <div className="border-t px-4 py-4 space-y-4 bg-muted/10">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatBlock label="Quality" value={`${qualityPct.toFixed(1)}%`} icon={<Gauge className="h-3.5 w-3.5" />} />
            <StatBlock label={ranking.tier === 'research' || ranking.tier === 'docs' ? 'Avg Run Time' : 'Avg Latency'} value={formatLatency(ranking.avg_latency_ms)} icon={<Clock className="h-3.5 w-3.5" />} />
            <StatBlock label="Total Cost" value={formatCurrency(ranking.total_cost)} icon={<DollarSign className="h-3.5 w-3.5" />} />
            <StatBlock
              label="Evals"
              value={`${ranking.num_evals}${ranking.errors > 0 ? ` (${ranking.errors} err)` : ''}`}
              icon={<Zap className="h-3.5 w-3.5" />}
            />
          </div>

          {/* Registry specs */}
          {registry && (
            <div className="rounded-md border bg-card p-3 space-y-2">
              <h4 className="text-xs font-medium text-muted-foreground">Model Specs</h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div>
                  <span className="text-muted-foreground">Context</span>
                  <p className="font-medium">{formatContext(registry.context_window)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Input</span>
                  <p className="font-medium">${registry.input_cost_per_1m}/MTok</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Output</span>
                  <p className="font-medium">${registry.output_cost_per_1m}/MTok</p>
                </div>
                <div>
                  <span className="text-muted-foreground">~Cost/query</span>
                  <p className="font-medium">{formatCurrency(registry.cost_per_query)}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {registry.specializations.map((s) => (
                  <span key={s} className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded capitalize">{s.replace(/_/g, ' ')}</span>
                ))}
              </div>
            </div>
          )}

          {radarData.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-md border bg-card p-3">
                <h4 className="text-xs font-medium text-muted-foreground mb-2">Task Performance</h4>
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData} margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
                      <PolarGrid stroke={CHART_THEME.grid.stroke} />
                      <PolarAngleAxis dataKey="task" tick={{ fontSize: 9, fill: CHART_THEME.axis.tick }} />
                      <Radar dataKey="score" stroke={MODEL_COLORS[0]} fill={MODEL_COLORS[0]} fillOpacity={0.2} strokeWidth={2} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="rounded-md border bg-card p-3">
                <h4 className="text-xs font-medium text-muted-foreground mb-2">Scores by Task</h4>
                <div className="space-y-1.5">
                  {Object.entries(ranking.scores_by_type)
                    .sort(([, a], [, b]) => b - a)
                    .map(([task, score]) => (
                      <div key={task} className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground w-28 truncate capitalize">{task.replace(/_/g, ' ')}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className={cn('h-full rounded-full', score >= 0.75 ? 'bg-green-500' : score >= 0.5 ? 'bg-yellow-500' : 'bg-red-500')}
                            style={{ width: `${score * 100}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono w-10 text-right">{(score * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          )}

          {results.length > 0 && (
            <div className="rounded-md border bg-card p-3">
              <h4 className="text-xs font-medium text-muted-foreground mb-2">Individual Evaluations</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground border-b">
                      <th className="text-left py-1.5 pr-3 font-medium">Task</th>
                      <th className="text-left py-1.5 pr-3 font-medium">Difficulty</th>
                      <th className="text-right py-1.5 pr-3 font-medium">Quality</th>
                      <th className="text-right py-1.5 pr-3 font-medium">Latency</th>
                      {results.some((r) => r.citation_count > 0) && (
                        <th className="text-right py-1.5 font-medium">Citations</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-1.5 pr-3 capitalize">{r.task_type.replace(/_/g, ' ')}</td>
                        <td className="py-1.5 pr-3">
                          <span className={cn(
                            'px-1.5 py-0.5 rounded text-[10px] font-medium',
                            r.difficulty === 'hard' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                            r.difficulty === 'medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                            'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          )}>
                            {r.difficulty}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono">
                          {r.error ? <span className="text-red-500">err</span> : `${(r.quality * 100).toFixed(0)}%`}
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono text-muted-foreground">
                          {formatLatency(r.latency_ms)}
                        </td>
                        {results.some((res) => res.citation_count > 0) && (
                          <td className="py-1.5 text-right font-mono text-muted-foreground">{r.citation_count || '-'}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Card for an unbenchmarked registry-only model */
function RegistryCard({
  model: m,
  isExpanded,
  onToggle,
}: {
  model: RegistryModel & { tier: string }
  isExpanded: boolean
  onToggle: () => void
}) {
  const modelName = m.model_key.split('/').pop() || m.model_key
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <button onClick={onToggle} className="w-full p-3 text-left hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 mb-1.5">
          <Cpu className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className="text-sm font-medium text-foreground truncate">{modelName}</span>
          <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded bg-muted shrink-0">{providerLabel(m.provider)}</span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span>{formatContext(m.context_window)} ctx</span>
          <span>${m.input_cost_per_1m}/${m.output_cost_per_1m} per MTok</span>
          <span>~{formatCurrency(m.cost_per_query)}/query</span>
        </div>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {m.specializations.slice(0, 4).map((s) => (
            <span key={s} className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded capitalize">{s.replace(/_/g, ' ')}</span>
          ))}
        </div>
      </button>
      {isExpanded && (
        <div className="border-t px-3 py-3 bg-muted/10 space-y-2">
          <div>
            <p className="text-[10px] font-medium text-muted-foreground mb-1">Strengths</p>
            <ul className="text-xs text-foreground space-y-0.5">
              {m.strengths.map((s, i) => <li key={i} className="flex gap-1.5"><span className="text-green-500 shrink-0">+</span> {s}</li>)}
            </ul>
          </div>
          {m.weaknesses.length > 0 && (
            <div>
              <p className="text-[10px] font-medium text-muted-foreground mb-1">Limitations</p>
              <ul className="text-xs text-foreground space-y-0.5">
                {m.weaknesses.map((w, i) => <li key={i} className="flex gap-1.5"><span className="text-muted-foreground shrink-0">-</span> {w}</li>)}
              </ul>
            </div>
          )}
          <p className="text-[10px] text-muted-foreground italic">Run a benchmark to see quality scores for this model.</p>
        </div>
      )}
    </div>
  )
}

function StatBlock({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <div className="text-muted-foreground">{icon}</div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-semibold text-foreground">{value}</p>
      </div>
    </div>
  )
}
