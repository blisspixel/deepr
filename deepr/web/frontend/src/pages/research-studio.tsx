import { useState, useCallback, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { cn, formatCurrency } from '@/lib/utils'
import { RESEARCH_MODES, MODELS, PRIORITIES } from '@/lib/constants'
import { toast } from 'sonner'
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

export default function ResearchStudio() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [prompt, setPrompt] = useState(searchParams.get('prompt') || '')
  const [mode, setMode] = useState<string>('research')
  const [model, setModel] = useState('o4-mini-deep-research')
  const [priority, setPriority] = useState(1)
  const [enableWebSearch, setEnableWebSearch] = useState(true)
  const [showConfig, setShowConfig] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [uploadedFileContents, setUploadedFileContents] = useState<{ name: string; content: string }[]>([])

  // Debounce prompt to avoid firing cost estimate on every keystroke
  const [debouncedPrompt, setDebouncedPrompt] = useState(prompt)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedPrompt(prompt), 500)
    return () => clearTimeout(timer)
  }, [prompt])

  // Cost estimate
  const { data: costEstimate, isLoading: isEstimating } = useQuery({
    queryKey: ['cost', 'estimate', debouncedPrompt, model, enableWebSearch],
    queryFn: () => costApi.estimate({ prompt: debouncedPrompt, model, enable_web_search: enableWebSearch }),
    enabled: debouncedPrompt.length > 10,
  })

  // Submit
  const submitMutation = useMutation({
    mutationFn: jobsApi.submit,
    onSuccess: (data) => {
      navigate(`/research/${data.job.id}`)
    },
    onError: () => {
      toast.error('Failed to submit research', {
        description: 'Check your API keys and budget limits.',
      })
    },
  })

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    const readResults = await Promise.all(
      files.map(file =>
        new Promise<{ file: File; name: string; content: string }>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = (event) => resolve({ file, name: file.name, content: event.target?.result as string })
          reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
          reader.readAsText(file)
        }).catch((err) => {
          console.warn(`Failed to read file ${file.name}:`, err)
          return null
        })
      )
    )
    const successful = readResults.filter((r): r is { file: File; name: string; content: string } => r !== null)
    if (successful.length > 0) {
      setUploadedFiles(prev => [...prev, ...successful.map(s => s.file)])
      setUploadedFileContents(prev => [...prev, ...successful.map(s => ({ name: s.name, content: s.content }))])
    }
    if (successful.length < files.length) {
      toast.warning(`Failed to read ${files.length - successful.length} file(s)`)
    }
  }, [])

  const removeFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index))
    setUploadedFileContents(prev => prev.filter((_, i) => i !== index))
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

  const isAllowed = costEstimate?.allowed ?? true

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Research Studio</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Configure and submit research tasks</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Main Input Card */}
        <div className="rounded-lg border bg-card overflow-hidden">
          {/* Prompt */}
          <div className="p-4">
            <label className="block text-sm font-medium text-foreground mb-2">
              What do you want to research?
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe your research question in detail. Be specific about what information you need, sources to prioritize, and desired output format..."
              rows={6}
              className="w-full px-3 py-2 bg-background border rounded-lg text-foreground text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
            />
            <div className="flex justify-between text-xs text-muted-foreground mt-1">
              <span>Be specific for best results</span>
              <span>{prompt.length} chars</span>
            </div>
          </div>

          {/* Mode Selector */}
          <div className="px-4 pb-3">
            <div className="flex gap-1 p-1 bg-secondary rounded-lg">
              {RESEARCH_MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setMode(m.value)}
                  className={cn(
                    'flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-all',
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
              className="w-full px-4 py-2.5 flex items-center justify-between text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <span className="font-medium">Configuration</span>
              {showConfig ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showConfig && (
              <div className="px-4 pb-4 space-y-4 animate-fade-in">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* Model */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">Model</label>
                    <select
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      className="w-full px-3 py-2 bg-background border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      {MODELS.map((m) => (
                        <option key={m.value} value={m.value}>{m.label} ({m.description})</option>
                      ))}
                    </select>
                  </div>

                  {/* Priority */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">Priority</label>
                    <select
                      value={priority}
                      onChange={(e) => setPriority(parseInt(e.target.value))}
                      className="w-full px-3 py-2 bg-background border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      {PRIORITIES.map((p) => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* Web Search */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">Web Search</label>
                    <div className="flex items-center h-[38px] px-3 bg-background border rounded-lg">
                      <input
                        type="checkbox"
                        checked={enableWebSearch}
                        onChange={(e) => setEnableWebSearch(e.target.checked)}
                        className="h-4 w-4 rounded border-input"
                        id="web-search"
                      />
                      <label htmlFor="web-search" className="ml-2 text-sm text-foreground cursor-pointer">
                        Enable
                      </label>
                    </div>
                  </div>
                </div>

                {/* File Upload */}
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Context Files</label>
                  <div className="border-2 border-dashed rounded-lg p-4 text-center hover:border-primary/30 transition-colors">
                    <input
                      type="file"
                      id="file-upload"
                      multiple
                      accept=".txt,.md,.json,.csv,.pdf"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    <label htmlFor="file-upload" className="cursor-pointer">
                      <FileUp className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                      <span className="text-sm text-foreground">Drop files or click to upload</span>
                      <p className="text-xs text-muted-foreground mt-0.5">TXT, MD, JSON, CSV, PDF</p>
                    </label>
                  </div>

                  {uploadedFiles.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {uploadedFiles.map((file, index) => (
                        <div key={`${file.name}-${index}`} className="flex items-center justify-between px-3 py-1.5 bg-secondary rounded">
                          <span className="text-xs text-foreground truncate">{file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
                          <button type="button" onClick={() => removeFile(index)} className="ml-2 text-muted-foreground hover:text-foreground">
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
          <div className="border-t px-4 py-3 flex items-center justify-between bg-muted/30">
            <div className="flex items-center gap-3">
              {isEstimating ? (
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

            <button
              type="submit"
              disabled={!prompt.trim() || !isAllowed || submitMutation.isPending}
              className={cn(
                'inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {submitMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              Submit
            </button>
          </div>
        </div>

        {/* Tips Card */}
        <div className="rounded-lg border bg-card p-4">
          <h3 className="text-sm font-medium text-foreground mb-2">Tips for better results</h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>Be specific about what information you need and desired output format</li>
            <li>Mention preferred sources (peer-reviewed, government data, industry reports)</li>
            <li>Use o4-mini for faster results, o3 for comprehensive research</li>
            <li>Upload reference documents for context-aware research</li>
          </ul>
        </div>
      </form>
    </div>
  )
}
