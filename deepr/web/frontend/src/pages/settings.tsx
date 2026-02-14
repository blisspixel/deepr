import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configApi } from '@/api/config'
import type { Config } from '@/types'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui-store'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertTriangle,
  CheckCircle,
  Database,
  DollarSign,
  HardDrive,
  Loader2,
  Monitor,
  Moon,
  Palette,
  Play,
  Server,
  Settings as SettingsIcon,
  Sun,
  XCircle,
} from 'lucide-react'
import { FormSkeleton } from '@/components/ui/skeleton'

export default function Settings() {
  const queryClient = useQueryClient()
  const { theme, setTheme } = useUIStore()

  const { data: config, isLoading, isError, refetch } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
  })

  const updateMutation = useMutation({
    mutationFn: (updates: Partial<Config>) => configApi.update(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      toast.success('Settings saved')
    },
    onError: () => {
      toast.error('Failed to save settings')
    },
  })

  const loadDemoMutation = useMutation({
    mutationFn: () => configApi.loadDemo(),
    onSuccess: (data) => {
      queryClient.invalidateQueries()
      toast.success(`Demo data loaded — ${data.created_jobs} sample jobs created`)
      if (data.errors?.length) {
        toast.warning(`Some demo data failed: ${data.errors[0]}`)
      }
    },
    onError: () => {
      toast.error('Failed to load demo data. Is the backend running?')
    },
  })

  const clearDemoMutation = useMutation({
    mutationFn: () => configApi.clearDemo(),
    onSuccess: (data) => {
      queryClient.invalidateQueries()
      toast.success(`Cleared ${data.cleared_jobs} jobs`)
    },
    onError: () => {
      toast.error('Failed to clear data')
    },
  })

  const [activeSection, setActiveSection] = useState('general')
  const [formData, setFormData] = useState({
    default_model: 'o4-mini-deep-research',
    default_priority: '1',
    enable_web_search: true,
    daily_limit: '100',
    monthly_limit: '1000',
  })

  useEffect(() => {
    if (config) {
      setFormData(prev => ({
        ...prev,
        default_model: config.default_model || prev.default_model,
        default_priority: config.default_priority?.toString() || prev.default_priority,
        enable_web_search: config.enable_web_search ?? prev.enable_web_search,
        daily_limit: config.daily_limit?.toString() || prev.daily_limit,
        monthly_limit: config.monthly_limit?.toString() || prev.monthly_limit,
      }))
    }
  }, [config])

  const handleChange = (field: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSave = () => {
    const updates: Record<string, unknown> = {}
    if (activeSection === 'general') {
      updates.default_model = formData.default_model
      updates.default_priority = parseInt(formData.default_priority)
      updates.enable_web_search = formData.enable_web_search
    } else if (activeSection === 'limits') {
      const daily = parseFloat(formData.daily_limit)
      const monthly = parseFloat(formData.monthly_limit)
      if (isNaN(daily) || isNaN(monthly) || daily < 0 || monthly < 0) {
        toast.error('Please enter valid budget amounts')
        return
      }
      updates.daily_limit = daily
      updates.monthly_limit = monthly
    }
    updateMutation.mutate(updates)
  }

  const sections = [
    { key: 'general', label: 'General', icon: SettingsIcon },
    { key: 'limits', label: 'Budget', icon: DollarSign },
    { key: 'appearance', label: 'Appearance', icon: Palette },
  ]

  if (isLoading) return <FormSkeleton />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <AlertTriangle className="w-10 h-10 text-muted-foreground/40 mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Unable to load settings</p>
        <p className="text-sm text-muted-foreground mb-4">Could not connect to the backend. Settings will appear here once the server is running.</p>
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
    <div className="max-w-4xl mx-auto p-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Configure Deepr for your environment</p>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        {/* Section Nav */}
        <div className="w-48 flex-shrink-0 space-y-1 hidden md:block">
          {sections.map((section) => (
            <button
              key={section.key}
              onClick={() => setActiveSection(section.key)}
              className={cn(
                'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors text-left',
                activeSection === section.key
                  ? 'bg-accent text-foreground font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
              )}
            >
              <section.icon className="w-4 h-4" />
              {section.label}
            </button>
          ))}
        </div>

        {/* Mobile section selector */}
        <div className="md:hidden w-full">
          <Select value={activeSection} onValueChange={setActiveSection}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sections.map(s => (
                <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-6">
          {activeSection === 'general' && (
            <>
              <div className="rounded-lg border bg-card p-5 space-y-5">
                <h2 className="text-base font-semibold text-foreground">General Settings</h2>
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <Label>Default Model</Label>
                    <Select
                      value={formData.default_model}
                      onValueChange={(v) => handleChange('default_model', v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="o4-mini-deep-research">o4-mini (Faster, Cheaper)</SelectItem>
                        <SelectItem value="o3-deep-research">o3 (More Thorough)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Default Priority</Label>
                    <Select
                      value={formData.default_priority}
                      onValueChange={(v) => handleChange('default_priority', v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">High</SelectItem>
                        <SelectItem value="3">Normal</SelectItem>
                        <SelectItem value="5">Low</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      id="web-search-default"
                      checked={formData.enable_web_search}
                      onCheckedChange={(checked) => handleChange('enable_web_search', checked)}
                    />
                    <Label htmlFor="web-search-default" className="cursor-pointer">
                      Enable web search by default
                    </Label>
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button onClick={handleSave} loading={updateMutation.isPending}>
                    Save
                  </Button>
                </div>
              </div>

              {/* Environment info */}
              <div className="rounded-lg border bg-card p-5 space-y-4">
                <h2 className="text-base font-semibold text-foreground">Environment</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                    <Server className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">Provider</p>
                      <p className="text-sm font-medium text-foreground capitalize">{config?.provider || 'openai'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                    <Database className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">Queue</p>
                      <p className="text-sm font-medium text-foreground capitalize">{config?.queue || 'sqlite'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                    <HardDrive className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">Storage</p>
                      <p className="text-sm font-medium text-foreground capitalize">{config?.storage || 'local'}</p>
                    </div>
                  </div>
                  {config?.provider_keys ? (
                    Object.entries(config.provider_keys).map(([provider, hasKey]) => (
                      <div key={provider} className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                        {hasKey ? (
                          <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 text-destructive flex-shrink-0" />
                        )}
                        <div>
                          <p className="text-xs text-muted-foreground">{provider}</p>
                          <p className="text-sm font-medium text-foreground">{hasKey ? 'Configured' : 'Not set'}</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                      {config?.has_api_key ? (
                        <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 text-destructive flex-shrink-0" />
                      )}
                      <div>
                        <p className="text-xs text-muted-foreground">API Key</p>
                        <p className="text-sm font-medium text-foreground">{config?.has_api_key ? 'Configured' : 'Not set'}</p>
                      </div>
                    </div>
                  )}
                </div>
                <div className="border-t pt-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">Demo Data</p>
                    <p className="text-xs text-muted-foreground">Load or clear sample data for exploring the UI. Set <code className="px-1 py-0.5 bg-muted rounded text-[10px]">DEEPR_DEMO=1</code> to auto-load on startup.</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => clearDemoMutation.mutate()}
                      disabled={clearDemoMutation.isPending}
                      className="inline-flex items-center gap-2 px-4 py-2 border rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      {clearDemoMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <XCircle className="w-4 h-4" />
                      )}
                      Clear
                    </button>
                    <button
                      onClick={() => loadDemoMutation.mutate()}
                      disabled={loadDemoMutation.isPending}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm font-medium hover:bg-secondary/80 transition-colors disabled:opacity-50"
                    >
                      {loadDemoMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                      {loadDemoMutation.isPending ? 'Loading...' : 'Load Demo'}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeSection === 'limits' && (
            <div className="rounded-lg border bg-card p-5 space-y-5">
              <h2 className="text-base font-semibold text-foreground">Budget Controls</h2>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label>Daily Spending Limit ($)</Label>
                  <Input
                    type="number"
                    step={0.01}
                    min={0}
                    value={formData.daily_limit}
                    onChange={(e) => handleChange('daily_limit', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Maximum per day</p>
                </div>
                <div className="space-y-1.5">
                  <Label>Monthly Spending Limit ($)</Label>
                  <Input
                    type="number"
                    step={0.01}
                    min={0}
                    value={formData.monthly_limit}
                    onChange={(e) => handleChange('monthly_limit', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Maximum per month</p>
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={handleSave} loading={updateMutation.isPending}>
                  Save Limits
                </Button>
              </div>
            </div>
          )}

          {activeSection === 'appearance' && (
            <div className="rounded-lg border bg-card p-5 space-y-5">
              <h2 className="text-base font-semibold text-foreground">Appearance</h2>
              <div>
                <Label className="mb-2 block">Theme</Label>
                <div className="grid grid-cols-3 gap-2">
                  {([
                    { key: 'light' as const, label: 'Light', icon: Sun },
                    { key: 'dark' as const, label: 'Dark', icon: Moon },
                    { key: 'system' as const, label: 'System', icon: Monitor },
                  ]).map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setTheme(t.key)}
                      className={cn(
                        'flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-all',
                        theme === t.key
                          ? 'border-primary bg-primary/5 text-foreground'
                          : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent/50'
                      )}
                    >
                      <t.icon className="w-4 h-4" />
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
