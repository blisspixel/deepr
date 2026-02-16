import { useState } from 'react'
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
    description: 'GPT-5.2, GPT-5, GPT-4.1, o3/o4-mini deep research',
    models: ['gpt-5.2', 'gpt-5', 'gpt-5-mini', 'gpt-4.1', 'gpt-4.1-mini', 'o3-deep-research', 'o4-mini-deep-research'],
    free: false,
  },
  {
    provider: 'Anthropic',
    envVar: 'ANTHROPIC_API_KEY',
    url: 'https://console.anthropic.com/settings/keys',
    description: 'Claude Opus 4.6, Sonnet 4.5, Haiku 4.5',
    models: ['claude-opus-4-6', 'claude-sonnet-4-5', 'claude-haiku-4-5'],
    free: false,
  },
  {
    provider: 'Google Gemini',
    envVar: 'GEMINI_API_KEY',
    url: 'https://aistudio.google.com/apikey',
    description: 'Gemini 3 Pro/Flash, 2.5 Pro/Flash, Deep Research',
    models: ['gemini-3-pro-preview', 'gemini-3-flash-preview', 'gemini-2.5-pro', 'gemini-2.5-flash', 'deep-research'],
    free: true,
  },
  {
    provider: 'xAI (Grok)',
    envVar: 'XAI_API_KEY',
    url: 'https://console.x.ai/',
    description: 'Grok 4 with live web search and news citations',
    models: ['grok-4-fast', 'grok-4-fast-reasoning', 'grok-4-1-fast-reasoning'],
    free: false,
  },
]

function Accordion({ title, icon, children, defaultOpen }: { title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
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
  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Help</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Get started with Deepr, configure API keys, and understand the platform.
        </p>
      </div>

      {/* What is Deepr */}
      <div className="rounded-lg border bg-card p-5 space-y-3">
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          What is Deepr?
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Deepr is a deep research automation platform. It orchestrates multiple AI models to produce
          comprehensive, cited research reports. Unlike single-model tools, Deepr routes queries to the
          best model for each task type, cross-references sources, and tracks costs.
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
              Set daily and monthly budgets. Auto-routing picks the most cost-effective model for each query.
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

      {/* API Keys */}
      <Accordion title="API Keys Setup" icon={<Key className="h-4 w-4" />} defaultOpen>
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Deepr needs API keys from at least one provider. Add them to your <code className="px-1.5 py-0.5 bg-muted rounded text-[11px]">.env</code> file
            or set as environment variables. More providers = better model routing.
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
# At minimum, set one of:
#   OPENAI_API_KEY=sk-...
#   GEMINI_API_KEY=AI...
#   ANTHROPIC_API_KEY=sk-ant-...
#   XAI_API_KEY=xai-...`}
            </pre>
            <p className="text-xs text-muted-foreground mt-2">
              Then configure your budget in{' '}
              <a href="/settings" className="text-primary hover:underline">Settings &rarr; Budget</a>
              {' '}or{' '}
              <a href="/costs" className="text-primary hover:underline">Cost Intelligence</a>.
            </p>
          </div>
        </div>
      </Accordion>

      {/* CLI Quick Reference */}
      <Accordion title="CLI Quick Reference" icon={<Terminal className="h-4 w-4" />}>
        <div className="space-y-3">
          <div className="space-y-2">
            {[
              { cmd: 'deepr "your research question"', desc: 'Run a deep research query' },
              { cmd: 'deepr --mode extended "topic"', desc: 'Extended mode with more sources' },
              { cmd: 'deepr news "breaking story"', desc: 'News research with live web search' },
              { cmd: 'deepr expert make my-expert', desc: 'Create a domain expert' },
              { cmd: 'deepr expert learn my-expert "topic"', desc: 'Teach an expert about a topic' },
              { cmd: 'deepr expert chat my-expert', desc: 'Chat with a domain expert' },
              { cmd: 'deepr budget set 10', desc: 'Set daily budget to $10' },
              { cmd: 'deepr budget status', desc: 'Check budget usage' },
              { cmd: 'deepr web', desc: 'Start the web UI' },
              { cmd: 'deepr mcp', desc: 'Start as MCP server (for Claude Desktop, etc.)' },
            ].map(({ cmd, desc }) => (
              <div key={cmd} className="flex gap-3 items-baseline">
                <code className="text-[11px] font-mono bg-muted px-2 py-0.5 rounded shrink-0">{cmd}</code>
                <span className="text-xs text-muted-foreground">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </Accordion>

      {/* Model Tiers */}
      <Accordion title="Understanding Model Tiers" icon={<FileText className="h-4 w-4" />}>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Deepr categorizes models into tiers based on task type. Auto-routing selects the best model for each query.
          </p>
          <div className="space-y-2">
            <div className="rounded-md border p-3">
              <p className="text-xs font-medium text-foreground">Research (Deep Research)</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Multi-step browsing, synthesis, and comprehensive reports. Uses o3-deep-research, o4-mini, Gemini Deep Research.
                Most expensive but most thorough.
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs font-medium text-foreground">News</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Real-time information with source citations. Uses Grok (live X/web access), Gemini with grounding.
                Best for current events and trending topics.
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs font-medium text-foreground">Chat</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Quick lookups, technical docs, reasoning, synthesis. Uses the broadest range of models.
                Auto-routing picks based on complexity and budget.
              </p>
            </div>
          </div>
        </div>
      </Accordion>

      {/* Footer */}
      <div className="text-xs text-muted-foreground text-center py-4">
        Deepr v2.9.0 &middot; MIT License &middot;{' '}
        <a href="https://github.com/langjam/deepr" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
          GitHub
        </a>
      </div>
    </div>
  )
}
