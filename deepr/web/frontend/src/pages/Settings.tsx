import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configApi } from '@/api/config'
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
  Database,
  DollarSign,
  Eye,
  EyeOff,
  Key,
  Monitor,
  Moon,
  Palette,
  Settings as SettingsIcon,
  Sun,
} from 'lucide-react'

export default function Settings() {
  const queryClient = useQueryClient()
  const { theme, setTheme } = useUIStore()

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
  })

  const updateMutation = useMutation({
    mutationFn: (updates: Record<string, unknown>) => configApi.update(updates as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      toast.success('Settings saved')
    },
    onError: () => {
      toast.error('Failed to save settings')
    },
  })

  const testMutation = useMutation({
    mutationFn: (provider: 'openai' | 'azure') => configApi.testConnection(provider),
    onSuccess: (_data, provider) => {
      toast.success(`${provider === 'openai' ? 'OpenAI' : 'Azure'} connection successful`)
    },
    onError: (_err, provider) => {
      toast.error(`${provider === 'openai' ? 'OpenAI' : 'Azure'} connection failed`)
    },
  })

  const [activeSection, setActiveSection] = useState('general')
  const [showApiKey, setShowApiKey] = useState(false)
  const [formData, setFormData] = useState({
    default_model: 'o4-mini-deep-research',
    default_priority: '1',
    enable_web_search: true,
    openai_api_key: '',
    azure_api_key: '',
    azure_endpoint: '',
    daily_limit: '100',
    monthly_limit: '1000',
    max_concurrent_jobs: '5',
    storage_type: 'local',
    azure_connection_string: '',
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
        max_concurrent_jobs: config.max_concurrent_jobs?.toString() || prev.max_concurrent_jobs,
        storage_type: config.storage_type || prev.storage_type,
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
    } else if (activeSection === 'api') {
      if (formData.openai_api_key) updates.openai_api_key = formData.openai_api_key
      if (formData.azure_api_key) updates.azure_api_key = formData.azure_api_key
      if (formData.azure_endpoint) updates.azure_endpoint = formData.azure_endpoint
    } else if (activeSection === 'limits') {
      updates.daily_limit = parseFloat(formData.daily_limit)
      updates.monthly_limit = parseFloat(formData.monthly_limit)
      updates.max_concurrent_jobs = parseInt(formData.max_concurrent_jobs)
    } else if (activeSection === 'storage') {
      updates.storage_type = formData.storage_type
      if (formData.azure_connection_string) updates.azure_connection_string = formData.azure_connection_string
    }
    updateMutation.mutate(updates)
  }

  const sections = [
    { key: 'general', label: 'General', icon: SettingsIcon },
    { key: 'api', label: 'API Keys', icon: Key },
    { key: 'limits', label: 'Budget', icon: DollarSign },
    { key: 'storage', label: 'Storage', icon: Database },
    { key: 'appearance', label: 'Appearance', icon: Palette },
  ]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Configure Deepr for your environment</p>
      </div>

      <div className="flex gap-6">
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
          )}

          {activeSection === 'api' && (
            <div className="rounded-lg border bg-card p-5 space-y-5">
              <h2 className="text-base font-semibold text-foreground">API Configuration</h2>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label>OpenAI API Key</Label>
                  <div className="relative">
                    <Input
                      type={showApiKey ? 'text' : 'password'}
                      value={formData.openai_api_key}
                      onChange={(e) => handleChange('openai_api_key', e.target.value)}
                      placeholder="sk-..."
                      className="pr-10 font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <p className="text-xs text-muted-foreground">Required for OpenAI Deep Research</p>
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-xs"
                      onClick={() => testMutation.mutate('openai')}
                      loading={testMutation.isPending}
                    >
                      Test
                    </Button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>Azure API Key</Label>
                  <Input
                    type="password"
                    value={formData.azure_api_key}
                    onChange={(e) => handleChange('azure_api_key', e.target.value)}
                    placeholder="Your Azure API key"
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">Optional: For Azure OpenAI Service</p>
                </div>
                <div className="space-y-1.5">
                  <Label>Azure Endpoint</Label>
                  <Input
                    type="text"
                    value={formData.azure_endpoint}
                    onChange={(e) => handleChange('azure_endpoint', e.target.value)}
                    placeholder="https://your-resource.openai.azure.com"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={handleSave} loading={updateMutation.isPending}>
                  Save API Keys
                </Button>
              </div>
            </div>
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
                <div className="space-y-1.5">
                  <Label>Max Concurrent Jobs</Label>
                  <Input
                    type="number"
                    step={1}
                    min={1}
                    max={20}
                    value={formData.max_concurrent_jobs}
                    onChange={(e) => handleChange('max_concurrent_jobs', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">1-20</p>
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={handleSave} loading={updateMutation.isPending}>
                  Save Limits
                </Button>
              </div>
            </div>
          )}

          {activeSection === 'storage' && (
            <div className="rounded-lg border bg-card p-5 space-y-5">
              <h2 className="text-base font-semibold text-foreground">Storage Configuration</h2>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label>Storage Type</Label>
                  <Select
                    value={formData.storage_type}
                    onValueChange={(v) => handleChange('storage_type', v)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="local">Local Storage (SQLite)</SelectItem>
                      <SelectItem value="azure">Azure Storage</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {formData.storage_type === 'azure' && (
                  <div className="space-y-1.5">
                    <Label>Connection String</Label>
                    <Input
                      type="password"
                      value={formData.azure_connection_string}
                      onChange={(e) => handleChange('azure_connection_string', e.target.value)}
                      placeholder="DefaultEndpointsProtocol=https;AccountName=..."
                      className="font-mono"
                    />
                  </div>
                )}
              </div>
              <div className="flex justify-end">
                <Button onClick={handleSave} loading={updateMutation.isPending}>
                  Save
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
