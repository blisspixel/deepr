import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import Card, { CardHeader, CardBody, CardFooter } from '@/components/common/Card'
import Button from '@/components/common/Button'
import TextArea from '@/components/common/TextArea'
import Select from '@/components/common/Select'

export default function SubmitResearch() {
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('o4-mini-deep-research')
  const [priority, setPriority] = useState('1')
  const [enableWebSearch, setEnableWebSearch] = useState(true)
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [uploadedFileContents, setUploadedFileContents] = useState<{name: string, content: string}[]>([])

  // Estimate cost
  const { data: costEstimate, isLoading: isEstimating } = useQuery({
    queryKey: ['cost', 'estimate', prompt, model, enableWebSearch],
    queryFn: () =>
      costApi.estimate({
        prompt,
        model,
        enable_web_search: enableWebSearch,
      }),
    enabled: prompt.length > 10,
  })

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: jobsApi.submit,
    onSuccess: () => {
      navigate('/jobs')
    },
  })

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    setUploadedFiles(prev => [...prev, ...files])

    // Read file contents
    for (const file of files) {
      const reader = new FileReader()
      reader.onload = (event) => {
        const content = event.target?.result as string
        setUploadedFileContents(prev => [...prev, { name: file.name, content }])
      }
      reader.readAsText(file)
    }
  }

  const removeFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index))
    setUploadedFileContents(prev => prev.filter((_, i) => i !== index))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!prompt.trim()) return

    // Include file contents in prompt if any
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
      priority: parseInt(priority),
      enable_web_search: enableWebSearch,
    })
  }

  const isAllowed = costEstimate?.allowed ?? true
  const characterCount = prompt.length

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          Submit Research
        </h1>
        <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          Create a new research task with detailed configuration
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        {/* Main Form */}
        <Card>
          <CardHeader>
            <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              Research Configuration
            </h2>
          </CardHeader>

          <CardBody className="space-y-6">
            {/* Prompt */}
            <div>
              <TextArea
                label="Research Prompt"
                placeholder="Describe what you want to research. Be specific about what information you need, sources to prioritize, and output format..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={8}
                required
              />
              <div className="flex justify-between text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                <span>Be clear and specific for best results</span>
                <span>{characterCount} characters</span>
              </div>
            </div>

            {/* Document Upload */}
            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: 'var(--color-text-secondary)' }}>
                Reference Documents (Optional)
              </label>
              <div
                className="border-2 border-dashed rounded-lg p-6 text-center"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <input
                  type="file"
                  id="file-upload"
                  multiple
                  accept=".txt,.md,.json,.csv,.pdf"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <label
                  htmlFor="file-upload"
                  className="cursor-pointer font-medium"
                  style={{ color: 'var(--color-text-primary)' }}
                >
                  Click to upload files
                </label>
                <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                  TXT, MD, JSON, CSV, PDF up to 10MB each
                </p>
              </div>

              {/* Uploaded Files List */}
              {uploadedFiles.length > 0 && (
                <div className="mt-3 space-y-2">
                  {uploadedFiles.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 rounded"
                      style={{ backgroundColor: 'var(--color-surface)' }}
                    >
                      <span className="text-sm truncate flex-1" style={{ color: 'var(--color-text-primary)' }}>
                        {file.name} ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="text-sm ml-2"
                        style={{ color: 'var(--color-text-secondary)' }}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Configuration Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Model */}
              <Select
                label="Model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                options={[
                  { value: 'o4-mini-deep-research', label: 'o4-mini (Faster, Cheaper)' },
                  { value: 'o3-deep-research', label: 'o3 (More Thorough, Expensive)' },
                ]}
              />

              {/* Priority */}
              <Select
                label="Priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                options={[
                  { value: '1', label: 'High Priority' },
                  { value: '3', label: 'Normal Priority' },
                  { value: '5', label: 'Low Priority' },
                ]}
              />

              {/* Web Search */}
              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                  Web Search
                </label>
                <div
                  className="flex items-center h-10 px-3 py-2 rounded-md"
                  style={{
                    backgroundColor: 'var(--color-bg)',
                    border: '1px solid var(--color-border)'
                  }}
                >
                  <input
                    type="checkbox"
                    checked={enableWebSearch}
                    onChange={(e) => setEnableWebSearch(e.target.checked)}
                    className="h-4 w-4 rounded"
                  />
                  <label className="ml-2 text-sm" style={{ color: 'var(--color-text-primary)' }}>
                    Enable web search
                  </label>
                </div>
              </div>
            </div>

            {/* Cost Estimate Panel */}
            <Card style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
              <CardBody>
                <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>
                  Cost Estimate
                </h3>

                {isEstimating ? (
                  <div className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    Calculating estimate...
                  </div>
                ) : costEstimate ? (
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                        Expected Cost:
                      </span>
                      <span className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>
                        ${costEstimate.estimate.expected_cost.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between items-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                      <span>Range:</span>
                      <span>
                        ${costEstimate.estimate.min_cost.toFixed(2)} - $
                        {costEstimate.estimate.max_cost.toFixed(2)}
                      </span>
                    </div>

                    {!isAllowed && (
                      <div
                        className="mt-3 p-3 rounded-md"
                        style={{
                          backgroundColor: 'var(--color-surface)',
                          border: '1px solid var(--color-border)'
                        }}
                      >
                        <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                          Warning: {costEstimate.reason}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    Enter a prompt to see cost estimate
                  </div>
                )}
              </CardBody>
            </Card>
          </CardBody>

          <CardFooter>
            <div className="flex justify-end space-x-3">
              <Button type="button" variant="ghost" onClick={() => navigate('/')}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!prompt.trim() || !isAllowed || submitMutation.isPending}
                isLoading={submitMutation.isPending}
              >
                Submit Research
              </Button>
            </div>
          </CardFooter>
        </Card>
      </form>

      {/* Tips */}
      <Card>
        <CardHeader>
          <h3 className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Tips for Better Results
          </h3>
        </CardHeader>
        <CardBody>
          <ul className="space-y-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            <li>• Be specific about what information you need</li>
            <li>• Mention preferred sources (e.g., peer-reviewed research, government data)</li>
            <li>• Request specific formats (e.g., "include statistics", "list key findings")</li>
            <li>• Ask for inline citations for verifiable claims</li>
            <li>• Use o4-mini for faster results, o3 for more comprehensive research</li>
          </ul>
        </CardBody>
      </Card>
    </div>
  )
}
