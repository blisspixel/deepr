export const MODELS = [
  { value: 'o4-mini-deep-research', label: 'o4-mini Deep Research', description: 'Fast, ~$2/query, ~1 min' },
  { value: 'o3-deep-research', label: 'o3 Deep Research', description: 'Thorough, ~$0.50/query, 2-5 min' },
  { value: 'gemini/deep-research', label: 'Gemini Deep Research', description: 'Google Search, ~$1/query, 5-20 min' },
] as const

export const PRIORITIES = [
  { value: 1, label: 'High' },
  { value: 3, label: 'Normal' },
  { value: 5, label: 'Low' },
] as const

export const RESEARCH_MODES = [
  { value: 'research', label: 'Research', description: 'Deep web research' },
  { value: 'check', label: 'Check', description: 'Fact verification' },
  { value: 'learn', label: 'Learn', description: 'Expert learning' },
  { value: 'team', label: 'Team', description: 'Multi-expert research' },
  { value: 'docs', label: 'Docs', description: 'Document analysis' },
] as const

export const JOB_STATUSES = {
  queued: { label: 'Queued', color: 'warning' },
  processing: { label: 'Running', color: 'info' },
  completed: { label: 'Completed', color: 'success' },
  failed: { label: 'Failed', color: 'destructive' },
  cancelled: { label: 'Cancelled', color: 'muted' },
} as const

export const TIME_RANGES = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
] as const

/** Default budget limits — used as fallbacks when backend is unreachable */
export const BUDGET_DEFAULTS = {
  PER_JOB: 10,
  DAILY: 10,
  MONTHLY: 100,
} as const

export const CHAT_MODES = [
  { value: 'ask', label: 'Ask', description: 'Quick answers — KB search only', color: 'bg-green-500' },
  { value: 'research', label: 'Research', description: 'Default — full tool access', color: 'bg-cyan-500' },
  { value: 'advise', label: 'Advise', description: 'Consulting-style structured advice', color: 'bg-yellow-500' },
  { value: 'focus', label: 'Focus', description: 'Deep reasoning — Tree of Thoughts', color: 'bg-purple-500' },
] as const

export const CHAT_COMMANDS: { name: string; aliases: string[]; description: string; category: string; args: string }[] = [
  // Mode
  { name: 'ask', aliases: [], description: 'Switch to Ask mode (KB only)', category: 'Mode', args: '' },
  { name: 'research', aliases: [], description: 'Switch to Research mode', category: 'Mode', args: '' },
  { name: 'advise', aliases: [], description: 'Switch to Advise mode', category: 'Mode', args: '' },
  { name: 'focus', aliases: [], description: 'Switch to Focus mode', category: 'Mode', args: '' },
  { name: 'mode', aliases: [], description: 'Show or switch mode', category: 'Mode', args: '[name]' },
  // Session
  { name: 'clear', aliases: [], description: 'Clear conversation', category: 'Session', args: '' },
  { name: 'compact', aliases: [], description: 'Compress conversation', category: 'Session', args: '[topic]' },
  { name: 'remember', aliases: [], description: 'Pin a fact', category: 'Session', args: '<text>' },
  { name: 'forget', aliases: ['unpin'], description: 'Remove pinned memory', category: 'Session', args: '<index>' },
  { name: 'memories', aliases: ['pins'], description: 'List pinned memories', category: 'Session', args: '' },
  { name: 'new', aliases: [], description: 'Start new conversation', category: 'Session', args: '' },
  // Reasoning
  { name: 'trace', aliases: [], description: 'Show reasoning trace', category: 'Reasoning', args: '' },
  { name: 'why', aliases: [], description: 'Explain last decision', category: 'Reasoning', args: '' },
  { name: 'decisions', aliases: [], description: 'List session decisions', category: 'Reasoning', args: '' },
  { name: 'thinking', aliases: [], description: 'Toggle thinking display', category: 'Reasoning', args: '[on|off]' },
  // Control
  { name: 'model', aliases: [], description: 'Show/change model', category: 'Control', args: '[name]' },
  { name: 'tools', aliases: [], description: 'List available tools', category: 'Control', args: '' },
  { name: 'effort', aliases: [], description: 'Set reasoning effort', category: 'Control', args: '[low|med|high]' },
  { name: 'budget', aliases: [], description: 'Show/set budget', category: 'Control', args: '[amount]' },
  // Management
  { name: 'save', aliases: [], description: 'Save conversation', category: 'Management', args: '[name]' },
  { name: 'export', aliases: [], description: 'Export as MD/JSON', category: 'Management', args: '[md|json]' },
  { name: 'council', aliases: [], description: 'Consult multiple experts', category: 'Management', args: '<query>' },
  { name: 'plan', aliases: [], description: 'Decompose into steps', category: 'Management', args: '<query>' },
  // Utility
  { name: 'help', aliases: ['?'], description: 'Show command help', category: 'Utility', args: '[command]' },
  { name: 'status', aliases: [], description: 'Session statistics', category: 'Utility', args: '' },
  { name: 'quit', aliases: ['exit', 'q'], description: 'End session', category: 'Utility', args: '' },
]
