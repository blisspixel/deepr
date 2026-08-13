import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import {
  Key,
  Zap,
  BookOpen,
  Users,
  DollarSign,
  ChevronDown,
  ExternalLink,
  Terminal,
  Globe,
  Search,
  FileText,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { healthApi } from '@/api/config'

interface ProviderKey {
  provider: string
  envVar: string
  url: string
  description: string
  models: string[]
  free: boolean
}

const API_KEYS: ProviderKey[] = [
  {
    provider: 'OpenAI',
    envVar: 'OPENAI_API_KEY',
    url: 'https://platform.openai.com/api-keys',
    description: 'GPT-5.6 family, GPT-5.5/5.4, and o3/o4-mini deep research',
    models: ['gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-5.5', 'gpt-5.4', 'o3-deep-research', 'o4-mini-deep-research'],
    free: false,
  },
  {
    provider: 'Anthropic',
    envVar: 'ANTHROPIC_API_KEY',
    url: 'https://console.anthropic.com/settings/keys',
    description: 'Claude Sonnet 5, Opus 5, and Haiku 4.5',
    models: ['claude-sonnet-5', 'claude-opus-5', 'claude-haiku-4-5'],
    free: false,
  },
  {
    provider: 'Google Gemini',
    envVar: 'GEMINI_API_KEY',
    url: 'https://aistudio.google.com/apikey',
    description: 'Gemini text and multimodal models; managed Deep Research remains gated',
    models: ['gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-3.1-pro-preview', 'gemini-2.5-pro'],
    free: true,
  },
  {
    provider: 'xAI (Grok)',
    envVar: 'XAI_API_KEY',
    url: 'https://console.x.ai/',
    description: 'Grok 4.6 frontier, Grok 4.3 cost-sensitive text, and Grok Build coding',
    models: ['grok-4.6', 'grok-4.3', 'grok-build-0.1'],
    free: false,
  },
]

function Accordion({ title, icon, children, defaultOpen }: { title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="text-muted-foreground">{icon}</div>
        <span className="flex-1 text-sm font-medium text-foreground">{title}</span>
        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && <div className="px-5 pb-5 pt-0">{children}</div>}
    </div>
  )
}

export default function Help() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => healthApi.get(),
  })

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Help</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Start with local diagnostics, inspect safe capacity, and add API keys only when needed.
        </p>
      </div>

      {/* What is Deepr */}
      <div className="rounded-lg border bg-card p-5 space-y-3">
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          What is Deepr?
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Deepr turns research into durable local state. Local, plan-quota, and metered paths have
          workflow-specific safety gates; source detection never authorizes execution. Persistent experts retain
          beliefs, gaps, citations, confidence, provenance, and cost records.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          <div className="rounded-md border p-3 space-y-1">
            <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Search className="h-3 w-3 text-primary" />
              Deep Research
            </p>
            <p className="text-xs text-muted-foreground">
              Multi-step research with web search, synthesis, and citation tracking. Best for comprehensive topics.
            </p>
          </div>
          <div className="rounded-md border p-3 space-y-1">
            <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Globe className="h-3 w-3 text-primary" />
              News Intelligence
            </p>
            <p className="text-xs text-muted-foreground">
              Real-time news monitoring with source attribution. Powered by models with live web access.
            </p>
          </div>
          <div className="rounded-md border p-3 space-y-1">
            <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Users className="h-3 w-3 text-primary" />
              Domain Experts
            </p>
            <p className="text-xs text-muted-foreground">
              Build persistent knowledge bases. Experts learn from documents, identify gaps, and answer questions.
            </p>
          </div>
          <div className="rounded-md border p-3 space-y-1">
            <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <DollarSign className="h-3 w-3 text-primary" />
              Cost Control
            </p>
            <p className="text-xs text-muted-foreground">
              Preview estimates, set hard budget ceilings, and keep every metered call in the append-only ledger.
            </p>
          </div>
        </div>
      </div>

      {/* When to use Deepr vs direct models */}
      <div className="rounded-lg border bg-card p-5 space-y-3">
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Zap className="h-4 w-4 text-muted-foreground" />
          When to use Deepr
        </h2>
        <div className="space-y-2">
          <div className="flex gap-3 items-start">
            <span className="text-xs font-semibold text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-2 py-0.5 rounded mt-0.5 shrink-0">USE DEEPR</span>
            <p className="text-sm text-muted-foreground">
              Researching many topics at scale, building knowledge bases over time,
              comparing information across sources, when you need cited reports with full attribution.
            </p>
          </div>
          <div className="flex gap-3 items-start">
            <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/30 px-2 py-0.5 rounded mt-0.5 shrink-0">ONE-OFF</span>
            <p className="text-sm text-muted-foreground">
              For a single quick report, you can also use
              <a href="https://chatgpt.com" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline mx-1">ChatGPT Deep Research</a>,
              <a href="https://gemini.google.com" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline mx-1">Gemini Deep Research</a>,
              or similar tools directly. Deepr shines when you need scale, cost control, and persistent knowledge.
            </p>
          </div>
        </div>
      </div>

      {/* Capacity */}
      <Accordion title="Capacity Setup" icon={<Key className="h-4 w-4" />} defaultOpen>
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Deepr can run through local Ollama, explicit plan-quota CLIs, metered API keys, or a mix.
            Add API keys to your <code className="px-1.5 py-0.5 bg-muted rounded text-[11px]">.env</code> file only when you want metered cloud capacity.
            Start with <code className="px-1.5 py-0.5 bg-muted rounded text-[11px]">capacity</code>, then use <code className="px-1.5 py-0.5 bg-muted rounded text-[11px]">capacity next</code> for local maintenance or <code className="px-1.5 py-0.5 bg-muted rounded text-[11px]">capacity fleet</code> for plan-adapter evidence.
          </p>
          <div className="space-y-3">
            {API_KEYS.map((key) => (
              <div key={key.provider} className="rounded-md border p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{key.provider}</span>
                    {key.free && (
                      <span className="text-[10px] font-medium text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-1.5 py-0.5 rounded">
                        Free tier available
                      </span>
                    )}
                  </div>
                  <a
                    href={key.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    Get key <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="text-xs text-muted-foreground">{key.description}</p>
                <div className="flex items-center gap-2">
                  <code className="text-[11px] font-mono bg-muted px-2 py-1 rounded">{key.envVar}=sk-...</code>
                </div>
                <div className="flex flex-wrap gap-1">
                  {key.models.map((m) => (
                    <span key={m} className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{m}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="rounded-md bg-muted/50 p-3 space-y-1.5">
            <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Terminal className="h-3 w-3" />
              Quick setup
            </p>
            <pre className="text-[11px] text-muted-foreground font-mono whitespace-pre-wrap">
{`# Copy the example env file
cp .env.example .env

# Edit with your keys
# Optional metered providers:
#   OPENAI_API_KEY=sk-...
#   GEMINI_API_KEY=AI...
#   ANTHROPIC_API_KEY=sk-ant-...
#   XAI_API_KEY=xai-...

# Capacity inspection starts with:
#   deepr init
#   deepr doctor --skip-connectivity
#   deepr capacity`}
            </pre>
            <p className="text-xs text-muted-foreground mt-2">
              Then configure your budget in{' '}
              <Link to="/settings" className="text-primary hover:underline">Settings</Link>
              {' '}or{' '}
              <Link to="/costs" className="text-primary hover:underline">Cost Intelligence</Link>.
            </p>
          </div>
        </div>
      </Accordion>

      {/* CLI Quick Reference */}
      <Accordion title="CLI Quick Reference" icon={<Terminal className="h-4 w-4" />}>
        <div className="space-y-3">
          <div className="space-y-2">
            {[
              { cmd: 'deepr research "your question" --auto --dry-run', desc: 'Preview route and cost before spending' },
              { cmd: 'deepr doctor --skip-connectivity', desc: 'Run local diagnostics without provider calls' },
              { cmd: 'deepr capacity', desc: 'Inventory detected, installed, and configured sources' },
              { cmd: 'deepr capacity next --task-class sync', desc: 'Show safe local-maintenance guidance' },
              { cmd: 'deepr capacity fleet', desc: 'Inspect plan-adapter eligibility and blockers' },
              { cmd: 'deepr expert make my-expert --local', desc: 'Create a local-only domain expert' },
              { cmd: 'deepr expert sync my-expert --local --fresh-context -y', desc: 'Refresh an expert on local capacity' },
              { cmd: 'deepr expert consult "what should change?" -e my-expert --local', desc: 'Consult stored expert knowledge locally' },
              { cmd: 'deepr costs show', desc: 'Check cost ledger totals' },
              { cmd: 'deepr costs estimate "prompt"', desc: 'Estimate before a metered call' },
              { cmd: 'deepr web', desc: 'Start the web UI' },
              { cmd: 'deepr mcp serve', desc: 'Start the MCP server for agent hosts' },
            ].map(({ cmd, desc }) => (
              <div key={cmd} className="flex flex-col gap-1 sm:flex-row sm:gap-3 sm:items-baseline">
                <code className="min-w-0 max-w-full whitespace-pre-wrap wrap-break-word text-[11px] font-mono bg-muted px-2 py-0.5 rounded">{cmd}</code>
                <span className="min-w-0 text-xs text-muted-foreground">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </Accordion>

      {/* Model Tiers */}
      <Accordion title="Understanding Model Tiers" icon={<FileText className="h-4 w-4" />}>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Deepr categorizes models by task. API research routing scores only configured, bounded API paths;
            local and plan capacity use separate workflow-specific gates.
          </p>
          <div className="space-y-2">
            <div className="rounded-md border p-3">
              <p className="text-xs font-medium text-foreground">Research (Deep Research)</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Multi-step browsing, synthesis, and comprehensive reports execute only when the exact provider, model,
                tools, context, output, and price envelope passes the current research gate.
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs font-medium text-foreground">News</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Fresh-context capability is provider and tool-envelope specific. Preview the exact path to see whether
                current pricing and tool bounds allow it.
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs font-medium text-foreground">Chat</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Expert consultation works through explicit local or safety-eligible plan synthesis. Legacy metered expert
                chat remains gated.
              </p>
            </div>
          </div>
        </div>
      </Accordion>

      {/* Footer */}
      <div className="text-xs text-muted-foreground text-center py-4">
        Deepr{health?.version ? ` v${health.version}` : ''} &middot; Apache 2.0 License &middot;{' '}
        <a href="https://github.com/blisspixel/deepr" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
          GitHub
        </a>
      </div>
    </div>
  )
}
