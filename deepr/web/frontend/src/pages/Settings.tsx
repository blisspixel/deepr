import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configApi } from '@/api/config'
import Card, { CardHeader, CardBody, CardFooter } from '@/components/common/Card'
import Button from '@/components/common/Button'
import Input from '@/components/common/Input'
import Select from '@/components/common/Select'

export default function Settings() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'general' | 'api' | 'limits' | 'storage'>('general')

  // Fetch current config
  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (updates: any) => configApi.update(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })

  const [formData, setFormData] = useState({
    // General
    default_model: config?.default_model || 'o4-mini-deep-research',
    default_priority: config?.default_priority || 1,
    enable_web_search: config?.enable_web_search ?? true,

    // API
    openai_api_key: config?.openai_api_key || '',
    azure_api_key: config?.azure_api_key || '',
    azure_endpoint: config?.azure_endpoint || '',

    // Limits
    daily_limit: config?.daily_limit || 100,
    monthly_limit: config?.monthly_limit || 1000,
    max_concurrent_jobs: config?.max_concurrent_jobs || 5,

    // Storage
    storage_type: config?.storage_type || 'local',
    azure_connection_string: config?.azure_connection_string || '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateMutation.mutate(formData)
  }

  const handleChange = (field: string, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          Configure Deepr for your environment
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex space-x-8">
          {[
            { id: 'general', label: 'General' },
            { id: 'api', label: 'API Keys' },
            { id: 'limits', label: 'Cost Limits' },
            { id: 'storage', label: 'Storage' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600 dark:border-primary-400 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <form onSubmit={handleSubmit}>
        {/* General Settings */}
        {activeTab === 'general' && (
          <Card>
            <CardHeader>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                General Settings
              </h2>
            </CardHeader>
            <CardBody className="space-y-4">
              <Select
                label="Default Model"
                value={formData.default_model}
                onChange={(e) => handleChange('default_model', e.target.value)}
                options={[
                  { value: 'o4-mini-deep-research', label: 'o4-mini (Faster, Cheaper)' },
                  { value: 'o3-deep-research', label: 'o3 (More Thorough)' },
                ]}
              />
              <Select
                label="Default Priority"
                value={formData.default_priority.toString()}
                onChange={(e) => handleChange('default_priority', parseInt(e.target.value))}
                options={[
                  { value: '1', label: 'High Priority' },
                  { value: '3', label: 'Normal Priority' },
                  { value: '5', label: 'Low Priority' },
                ]}
              />
              <div>
                <label className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    checked={formData.enable_web_search}
                    onChange={(e) => handleChange('enable_web_search', e.target.checked)}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Enable web search by default
                  </span>
                </label>
              </div>
            </CardBody>
            <CardFooter>
              <div className="flex justify-end">
                <Button type="submit" isLoading={updateMutation.isPending}>
                  Save Changes
                </Button>
              </div>
            </CardFooter>
          </Card>
        )}

        {/* API Keys */}
        {activeTab === 'api' && (
          <Card>
            <CardHeader>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                API Configuration
              </h2>
            </CardHeader>
            <CardBody className="space-y-4">
              <Input
                label="OpenAI API Key"
                type="password"
                value={formData.openai_api_key}
                onChange={(e) => handleChange('openai_api_key', e.target.value)}
                placeholder="sk-..."
                helperText="Required for OpenAI Deep Research"
              />
              <Input
                label="Azure API Key"
                type="password"
                value={formData.azure_api_key}
                onChange={(e) => handleChange('azure_api_key', e.target.value)}
                placeholder="Your Azure API key"
                helperText="Optional: For Azure OpenAI Service"
              />
              <Input
                label="Azure Endpoint"
                value={formData.azure_endpoint}
                onChange={(e) => handleChange('azure_endpoint', e.target.value)}
                placeholder="https://your-resource.openai.azure.com"
                helperText="Optional: Your Azure OpenAI endpoint"
              />
            </CardBody>
            <CardFooter>
              <div className="flex justify-end">
                <Button type="submit" isLoading={updateMutation.isPending}>
                  Save API Keys
                </Button>
              </div>
            </CardFooter>
          </Card>
        )}

        {/* Cost Limits */}
        {activeTab === 'limits' && (
          <Card>
            <CardHeader>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Budget Controls
              </h2>
            </CardHeader>
            <CardBody className="space-y-4">
              <Input
                label="Daily Spending Limit ($)"
                type="number"
                step="0.01"
                min="0"
                value={formData.daily_limit}
                onChange={(e) => handleChange('daily_limit', parseFloat(e.target.value))}
                helperText="Maximum amount to spend per day"
              />
              <Input
                label="Monthly Spending Limit ($)"
                type="number"
                step="0.01"
                min="0"
                value={formData.monthly_limit}
                onChange={(e) => handleChange('monthly_limit', parseFloat(e.target.value))}
                helperText="Maximum amount to spend per month"
              />
              <Input
                label="Max Concurrent Jobs"
                type="number"
                min="1"
                max="20"
                value={formData.max_concurrent_jobs}
                onChange={(e) => handleChange('max_concurrent_jobs', parseInt(e.target.value))}
                helperText="Maximum number of jobs running simultaneously"
              />
            </CardBody>
            <CardFooter>
              <div className="flex justify-end">
                <Button type="submit" isLoading={updateMutation.isPending}>
                  Save Limits
                </Button>
              </div>
            </CardFooter>
          </Card>
        )}

        {/* Storage */}
        {activeTab === 'storage' && (
          <Card>
            <CardHeader>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Storage Configuration
              </h2>
            </CardHeader>
            <CardBody className="space-y-4">
              <Select
                label="Storage Type"
                value={formData.storage_type}
                onChange={(e) => handleChange('storage_type', e.target.value)}
                options={[
                  { value: 'local', label: 'Local Storage (SQLite)' },
                  { value: 'azure', label: 'Azure Storage (Table Storage + Blob)' },
                ]}
              />
              {formData.storage_type === 'azure' && (
                <Input
                  label="Azure Connection String"
                  type="password"
                  value={formData.azure_connection_string}
                  onChange={(e) => handleChange('azure_connection_string', e.target.value)}
                  placeholder="DefaultEndpointsProtocol=https;AccountName=..."
                  helperText="Connection string for Azure Storage account"
                />
              )}
            </CardBody>
            <CardFooter>
              <div className="flex justify-end">
                <Button type="submit" isLoading={updateMutation.isPending}>
                  Save Storage Settings
                </Button>
              </div>
            </CardFooter>
          </Card>
        )}
      </form>

      {/* Success/Error Messages */}
      {updateMutation.isSuccess && (
        <Card className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
          <CardBody>
            <p className="text-green-800 dark:text-green-300">
              ✓ Settings saved successfully
            </p>
          </CardBody>
        </Card>
      )}
      {updateMutation.isError && (
        <Card className="bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
          <CardBody>
            <p className="text-red-800 dark:text-red-300">
              ✗ Failed to save settings. Please try again.
            </p>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
