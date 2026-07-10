import { useState, useCallback, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { configApi } from '@/api/config'
import { cn, formatCurrency } from '@/lib/utils'
import { RESEARCH_MODES, MODELS, PRIORITIES } from '@/lib/constants'
import {
  loadResearchDraft,
  removeResearchDraft,
  resolveInitialResearchPrompt,
  saveResearchDraft,
  type DraftConstraints,
} from '@/lib/research-draft'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  ChevronDown,
  ChevronUp,
  FileUp,
  Info,
  Loader2,
  Send,
  Sparkles,
  X,
} from 'lucide-react'

const RESEARCH_DRAFT_KEY = 'deepr.research-draft.v1'
const DEFAULT_MODEL = 'o4-mini-deep-research'
const draftStorage = () => window.sessionStorage
const DRAFT_CONSTRAINTS: DraftConstraints = {
  modes: RESEARCH_MODES.map((mode) => mode.value),
  models: MODELS.map((model) => model.value),
  priorities: PRIORITIES.map((priority) => priority.value),
}

export default function ResearchStudio() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [initialDraft] = useState(() => loadResearchDraft(
    RESEARCH_DRAFT_KEY,
    draftStorage,
    DRAFT_CONSTRAINTS,
  ))
  const [initialPrompt] = useState(() => resolveInitialResearchPrompt(
    initialDraft.draft?.prompt ?? null,
    searchParams.get('prompt'),
  ))
  const [prompt, setPrompt] = useState(initialPrompt.prompt)
  const [pendingPrefill, setPendingPrefill] = useState(initialPrompt.pendingPrefill)
  const [invalidPrefill, setInvalidPrefill] = useState(initialPrompt.invalidPrefill)
  const [mode, setMode] = useState<string>(initialDraft.draft?.mode || 'research')
  const [model, setModel] = useState(initialDraft.draft?.model || DEFAULT_MODEL)
  const [priority, setPriority] = useState(initialDraft.draft?.priority || 1)
  const [enableWebSearch, setEnableWebSearch] = useState(initialDraft.draft?.enableWebSearch ?? true)
  const [showConfig, setShowConfig] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [uploadedFileContents, setUploadedFileContents] = useState<{ name: string; content: string }[]>([])
  const [draftStatus, setDraftStatus] = useState<'idle' | 'restored' | 'saved'>(
    initialDraft.draft ? 'restored' : 'idle'
  )
  const [draftIssue, setDraftIssue] = useState(initialDraft.issue)

  const {
    data: config,
    isLoading: isConfigLoading,
    isError: isConfigError,
    refetch: refetchConfig,
  } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
  })

  useEffect(() => {
    if (!initialDraft.draft
      && config?.default_model
      && MODELS.some((candidate) => candidate.value === config.default_model)) {
      setModel(config.default_model)
    }
  }, [config?.default_model, initialDraft.draft])

  useEffect(() => {
    if (!prompt.trim()) {
      if (!invalidPrefill
        && !removeResearchDraft(RESEARCH_DRAFT_KEY, draftStorage)) {
        setDraftIssue('unavailable')
      }
      setDraftStatus('idle')
      return
    }

    const timer = setTimeout(() => {
      const saved = saveResearchDraft(
        RESEARCH_DRAFT_KEY,
        draftStorage,
        { version: 1, prompt, mode, model, priority, enableWebSearch },
        DRAFT_CONSTRAINTS,
      )
      if (saved) {
        setDraftIssue(null)
        setDraftStatus('saved')
      } else {
        setDraftIssue('unavailable')
        setDraftStatus('idle')
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [enableWebSearch, invalidPrefill, mode, model, priority, prompt])

  // Debounce prompt to avoid firing cost estimate on every keystroke
  const [debouncedPrompt, setDebouncedPrompt] = useState(prompt)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedPrompt(prompt), 500)
    return () => clearTimeout(timer)
  }, [prompt])

  // Cost estimate
  const {
    data: costEstimate,
    isFetching: isEstimating,
    isError: isEstimateError,
    refetch: refetchEstimate,
  } = useQuery({
    queryKey: ['cost', 'estimate', debouncedPrompt, model, enableWebSearch],
    queryFn: () => costApi.estimate({ prompt: debouncedPrompt, model, enable_web_search: enableWebSearch }),
    enabled: debouncedPrompt.trim().length > 0,
  })

  // Submit
  const submitMutation = useMutation({
    mutationFn: jobsApi.submit,
    onSuccess: (data) => {
      if (!removeResearchDraft(RESEARCH_DRAFT_KEY, draftStorage)) {
        toast.warning('Research submitted, but the saved draft could not be cleared in this browser.')
      }
      navigate(`/research/${data.job.id}`)
    },
    onError: (error: Error) => {
      toast.error('Failed to submit research', {
        description: error.message || 'The server rejected the submission.',
      })
    },
  })

  const processFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return
    const allowed = ['.txt', '.md', '.json', '.csv']
    // Size caps - uploaded content is inlined into the prompt; a 100 MB
    // CSV would silently push token usage into hundreds of dollars.
    const MAX_FILE_BYTES = 1 * 1024 * 1024 // 1 MB per file
    const MAX_TOTAL_BYTES = 5 * 1024 * 1024 // 5 MB across all files
    const filtered = files.filter(f => allowed.some(ext => f.name.toLowerCase().endsWith(ext)))
    if (filtered.length < files.length) {
      toast.warning(`${files.length - filtered.length} file(s) skipped (unsupported type)`)
    }
    const oversized = filtered.filter(f => f.size > MAX_FILE_BYTES)
    if (oversized.length > 0) {
      toast.error(`${oversized.length} file(s) exceed 1 MB and were skipped`, {
        description: oversized.map(f => `${f.name} (${Math.round(f.size / 1024)} KB)`).join(', '),
      })
    }
    const sized = filtered.filter(f => f.size <= MAX_FILE_BYTES)
    const totalBytes = sized.reduce((acc, f) => acc + f.size, 0)
    if (totalBytes > MAX_TOTAL_BYTES) {
      toast.error(`Combined upload size exceeds 5 MB; no files added`, {
        description: `Got ${Math.round(totalBytes / 1024)} KB. Trim the batch.`,
      })
      return
    }
    if (sized.length === 0) return
    const readResults = await Promise.all(
      sized.map(file =>
        new Promise<{ file: File; name: string; content: string }>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = (event) => {
            const result = event.target?.result
            if (typeof result === 'string') {
              resolve({ file, name: file.name, content: result })
            } else {
              reject(new Error(`FileReader returned non-string result for ${file.name}`))
            }
          }
          reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
          reader.readAsText(file)
        }).catch(() => {
          return null
        })
      )
    )
    const successful = readResults.filter((r): r is { file: File; name: string; content: string } => r !== null)
    if (successful.length > 0) {
      setUploadedFiles(prev => [...prev, ...successful.map(s => s.file)])
      setUploadedFileContents(prev => [...prev, ...successful.map(s => ({ name: s.name, content: s.content }))])
    }
    if (successful.length < sized.length) {
      toast.warning(`Failed to read ${sized.length - successful.length} file(s)`)
    }
  }, [])

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    processFiles(Array.from(e.target.files || []))
  }, [processFiles])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    processFiles(Array.from(e.dataTransfer.files))
  }, [processFiles])

  const removeFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index))
    setUploadedFileContents(prev => prev.filter((_, i) => i !== index))
  }

  const clearDraft = () => {
    setPrompt('')
    setMode('research')
    setModel(
      config?.default_model && MODELS.some((candidate) => candidate.value === config.default_model)
        ? config.default_model
        : DEFAULT_MODEL
    )
    setPriority(1)
    setEnableWebSearch(true)
    setUploadedFiles([])
    setUploadedFileContents([])
    setDraftStatus('idle')
    setPendingPrefill(null)
    setInvalidPrefill(false)
    setDraftIssue(removeResearchDraft(RESEARCH_DRAFT_KEY, draftStorage) ? null : 'unavailable')
  }

  const useLinkedPrompt = () => {
    if (!pendingPrefill) return
    setPrompt(pendingPrefill)
    setPendingPrefill(null)
    setInvalidPrefill(false)
    setDraftStatus('idle')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return

    let fullPrompt = prompt
    if (uploadedFileContents.length > 0) {
      fullPrompt += '\n\n---\n\nReference Documents:\n\n'
      uploadedFileContents.forEach(file => {
        fullPrompt += `\n## ${file.name}\n\`\`\`\n${file.content}\n\`\`\`\n`
      })
    }

    submitMutation.mutate({
      prompt: fullPrompt,
      model,
      priority,
      enable_web_search: enableWebSearch,
      mode,
    })
  }

  const requiresEstimate = Boolean(prompt.trim())
  const hasCurrentEstimate = !requiresEstimate || (
    debouncedPrompt === prompt && Boolean(costEstimate) && !isEstimateError
  )
  const isAllowed = hasCurrentEstimate && (costEstimate?.allowed ?? true)
  const providerReady = config?.has_api_key === true
  const canSubmit = Boolean(prompt.trim())
    && providerReady
    && !isConfigLoading
    && !isConfigError
    && isAllowed
    && !submitMutation.isPending

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Research Studio</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Configure and submit research tasks</p>
      </div>

      {isConfigError && (
        <div role="alert" className="rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 flex items-center gap-3">
          <Info className="w-4 h-4 text-warning flex-shrink-0" />
          <p className="text-sm text-muted-foreground flex-1">
            Provider readiness could not be verified. Research submission is paused.
          </p>
          <button type="button" onClick={() => refetchConfig()} className="text-sm text-primary hover:underline">
            Retry
          </button>
        </div>
      )}

      {config && !providerReady && (
        <div role="alert" className="rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 flex items-start gap-3">
          <Info className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
          <p className="text-sm text-muted-foreground">
            Dashboard research currently requires OpenAI, but <code className="text-xs">OPENAI_API_KEY</code> is not set.
            Add the key and restart Deepr before submitting. Other configured providers remain available through CLI workflows.{' '}
            <Link to="/help" className="text-primary hover:underline">View capacity setup</Link>.
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Main Input Card */}
        <div className="rounded-lg border bg-card overflow-hidden">
          {/* Prompt */}
          <div className="p-4">
            <label htmlFor="research-prompt" className="block text-sm font-medium text-foreground mb-2">
              What do you want to research?
            </label>
            <textarea
              id="research-prompt"
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                setInvalidPrefill(false)
                setDraftStatus('idle')
              }}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                  e.preventDefault()
                  if (canSubmit) {
                    handleSubmit(e as unknown as React.FormEvent)
                  }
                }
              }}
              placeholder="Describe your research question in detail. Be specific about what information you need, sources to prioritize, and desired output format..."
              rows={6}
              maxLength={50000}
              className="w-full px-3 py-2 bg-background border rounded-lg text-foreground text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
            />
            <div className="flex justify-between gap-3 text-xs text-muted-foreground mt-1">
              <span>Be specific for best results</span>
              <span>{prompt.length} chars</span>
            </div>
            {invalidPrefill && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                The linked prompt exceeded 50,000 characters and was not loaded.
              </p>
            )}
            {pendingPrefill && (
              <div role="alert" className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-warning">
                <span>A linked prompt is ready. Your saved draft was preserved.</span>
                <span className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={useLinkedPrompt}
                    className="inline-flex min-h-11 items-center px-2 underline underline-offset-2 hover:text-foreground"
                  >
                    Use linked prompt
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingPrefill(null)}
                    className="inline-flex min-h-11 items-center px-2 underline underline-offset-2 hover:text-foreground"
                  >
                    Keep draft
                  </button>
                </span>
              </div>
            )}
            {(prompt.trim() || draftIssue) && (
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                {draftIssue === 'unavailable' ? (
                  <span role="alert" className="text-destructive">
                    Draft recovery is unavailable in this browser. Do not navigate away from this form.
                  </span>
                ) : draftIssue === 'discarded' ? (
                  <span role="alert" className="text-warning">
                    An invalid saved draft was discarded.
                  </span>
                ) : (
                  <span role="status" className="text-muted-foreground">
                    {draftStatus === 'restored'
                      ? 'Draft restored in this tab.'
                      : draftStatus === 'saved'
                        ? 'Draft saved in this tab.'
                        : 'Saving draft in this tab.'}{' '}
                    Context files are not saved.
                  </span>
                )}
                {prompt.trim() && (
                  <button
                    type="button"
                    onClick={clearDraft}
                    className="inline-flex min-h-11 items-center px-2 text-muted-foreground underline underline-offset-2 hover:text-foreground"
                  >
                    Clear draft
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Mode Selector */}
          <div className="px-4 pb-3">
            <div role="group" aria-label="Research mode" className="grid grid-cols-2 gap-1 rounded-lg bg-secondary p-1 sm:grid-cols-5">
              {RESEARCH_MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => {
                    setMode(m.value)
                    setDraftStatus('idle')
                  }}
                  aria-pressed={mode === m.value}
                  className={cn(
                    'min-h-11 rounded-md px-2 py-1.5 text-xs font-medium transition-all sm:px-3',
                    mode === m.value
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Configuration Panel */}
          <div className="border-t">
            <button
              type="button"
              onClick={() => setShowConfig(!showConfig)}
              aria-expanded={showConfig}
              aria-controls="research-configuration"
              className="w-full px-4 py-2.5 flex items-center justify-between text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <span className="font-medium">Configuration</span>
              {showConfig ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showConfig && (
              <div id="research-configuration" className="px-4 pb-4 space-y-4 animate-fade-in">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* Model */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">OpenAI model</label>
                    <Select
                      value={model}
                      onValueChange={(value) => {
                        setModel(value)
                        setDraftStatus('idle')
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {MODELS.map((m) => (
                          <SelectItem key={m.value} value={m.value}>{m.label} ({m.description})</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Priority */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">Priority</label>
                    <Select
                      value={priority.toString()}
                      onValueChange={(value) => {
                        setPriority(parseInt(value))
                        setDraftStatus('idle')
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PRIORITIES.map((p) => (
                          <SelectItem key={p.value} value={p.value.toString()}>{p.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Web Search */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">Web Search</label>
                    <div className="flex items-center h-[38px] px-3 bg-background border rounded-lg">
                      <input
                        type="checkbox"
                        checked={enableWebSearch}
                        onChange={(e) => {
                          setEnableWebSearch(e.target.checked)
                          setDraftStatus('idle')
                        }}
                        className="h-4 w-4 rounded border-input"
                        id="web-search"
                      />
                      <label htmlFor="web-search" className="ml-2 text-sm text-foreground cursor-pointer">
                        Enable
                      </label>
                    </div>
                  </div>
                </div>

                <p className="text-xs text-muted-foreground">
                  Dashboard research uses the OpenAI background-research API. Use the CLI for Gemini, xAI, local, or plan-quota capacity.
                </p>

                {/* File Upload */}
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Context Files</label>
                  <div
                    className={cn(
                      'border-2 border-dashed rounded-lg p-4 text-center transition-colors',
                      isDragging ? 'border-primary bg-primary/5' : 'hover:border-primary/30'
                    )}
                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                    onDragEnter={(e) => { e.preventDefault(); setIsDragging(true) }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                  >
                    <input
                      type="file"
                      id="file-upload"
                      multiple
                      accept=".txt,.md,.json,.csv"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    <label htmlFor="file-upload" className="cursor-pointer">
                      <FileUp className={cn('w-5 h-5 mx-auto mb-1', isDragging ? 'text-primary' : 'text-muted-foreground')} />
                      <span className="text-sm text-foreground">{isDragging ? 'Drop files here' : 'Drop files or click to upload'}</span>
                      <p className="text-xs text-muted-foreground mt-0.5">TXT, MD, JSON, CSV</p>
                    </label>
                  </div>

                  {uploadedFiles.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {uploadedFiles.map((file, index) => (
                        <div key={`${file.name}-${index}`} className="flex items-center justify-between px-3 py-1.5 bg-secondary rounded">
                          <span className="text-xs text-foreground truncate">{file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
                          <button
                            type="button"
                            onClick={() => removeFile(index)}
                            aria-label={`Remove ${file.name}`}
                            className="ml-2 inline-flex h-11 w-11 flex-shrink-0 items-center justify-center text-muted-foreground hover:text-foreground"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Cost Estimate + Submit */}
          <div className="border-t px-4 py-3 flex flex-col gap-3 bg-muted/30 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {isEstimateError ? (
                <span role="alert" className="flex items-center gap-1.5 text-xs text-destructive">
                  <Info className="w-3 h-3" />
                  Estimate unavailable.
                  <button type="button" onClick={() => refetchEstimate()} className="underline underline-offset-2">
                    Retry
                  </button>
                </span>
              ) : isEstimating || (requiresEstimate && debouncedPrompt !== prompt) ? (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Estimating...
                </span>
              ) : costEstimate ? (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Sparkles className="w-3 h-3" />
                  Est. {formatCurrency(costEstimate.estimate.expected_cost)}
                  <span className="text-muted-foreground/60">
                    ({formatCurrency(costEstimate.estimate.min_cost)}-{formatCurrency(costEstimate.estimate.max_cost)})
                  </span>
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">Type a prompt to estimate cost</span>
              )}

              {!isAllowed && costEstimate?.reason && (
                <span className="flex items-center gap-1 text-xs text-destructive">
                  <Info className="w-3 h-3" />
                  {costEstimate.reason}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 self-end sm:self-auto">
              <kbd className="hidden sm:inline text-[10px] text-muted-foreground/60 font-mono">
                {navigator.platform?.includes('Mac') ? '\u2318+\u21A9' : 'Ctrl+\u21B5'}
              </kbd>
              <Button
                type="submit"
                disabled={!canSubmit}
                loading={submitMutation.isPending}
              >
                <Send className="w-4 h-4" />
                Submit
              </Button>
            </div>
          </div>
        </div>

        {/* Tips Card */}
        <div className="rounded-lg border bg-card p-4">
          <h3 className="text-sm font-medium text-foreground mb-2">Tips for better results</h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>Be specific about what information you need and desired output format</li>
            <li>Mention preferred sources (peer-reviewed, government data, industry reports)</li>
            <li>Use o4-mini for faster results or o3 for more thorough OpenAI deep research</li>
            <li>Open Configuration to upload reference documents for this submission</li>
          </ul>
        </div>
      </form>
    </div>
  )
}
