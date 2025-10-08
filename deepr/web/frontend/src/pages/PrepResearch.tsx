import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { plannerApi } from '@/api/planner'
import Card, { CardHeader, CardBody, CardFooter } from '@/components/common/Card'
import Button from '@/components/common/Button'
import TextArea from '@/components/common/TextArea'
import Input from '@/components/common/Input'
import Select from '@/components/common/Select'

interface PlannedTask {
  title: string
  prompt: string
  estimated_cost?: number
}

export default function PrepResearch() {
  const navigate = useNavigate()
  const [scenario, setScenario] = useState('')
  const [context, setContext] = useState('')
  const [maxTasks, setMaxTasks] = useState(5)
  const [plannerModel, setPlannerModel] = useState('gpt-5-mini')
  const [researchModel, setResearchModel] = useState('o4-mini-deep-research')
  const [enableWebSearch, setEnableWebSearch] = useState(true)
  const [priority, setPriority] = useState(3)

  const [plannedTasks, setPlannedTasks] = useState<PlannedTask[]>([])
  const [selectedTasks, setSelectedTasks] = useState<Set<number>>(new Set())

  // Plan research mutation
  const planMutation = useMutation({
    mutationFn: plannerApi.plan,
    onSuccess: (data) => {
      setPlannedTasks(data.plan)
      // Select all tasks by default
      setSelectedTasks(new Set(data.plan.map((_, idx) => idx)))
    },
  })

  // Execute plan mutation
  const executeMutation = useMutation({
    mutationFn: plannerApi.execute,
    onSuccess: (data) => {
      navigate(`/batch/${data.batch_id}`)
    },
  })

  const handlePlan = (e: React.FormEvent) => {
    e.preventDefault()
    if (!scenario.trim()) return

    planMutation.mutate({
      scenario: scenario.trim(),
      max_tasks: maxTasks,
      context: context.trim() || undefined,
      planner_model: plannerModel,
      research_model: researchModel,
      enable_web_search: enableWebSearch,
    })
  }

  const handleExecute = () => {
    if (selectedTasks.size === 0) return

    const tasksToExecute = Array.from(selectedTasks).map((idx) => plannedTasks[idx])

    executeMutation.mutate({
      scenario,
      tasks: tasksToExecute,
      model: researchModel,
      priority,
      enable_web_search: enableWebSearch,
    })
  }

  const toggleTask = (idx: number) => {
    const newSelected = new Set(selectedTasks)
    if (newSelected.has(idx)) {
      newSelected.delete(idx)
    } else {
      newSelected.add(idx)
    }
    setSelectedTasks(newSelected)
  }

  const toggleAll = () => {
    if (selectedTasks.size === plannedTasks.length) {
      setSelectedTasks(new Set())
    } else {
      setSelectedTasks(new Set(plannedTasks.map((_, idx) => idx)))
    }
  }

  const totalCost = Array.from(selectedTasks).reduce((sum, idx) => {
    return sum + (plannedTasks[idx]?.estimated_cost || 0)
  }, 0)

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Prep Research</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          Plan multi-angle research strategy using GPT-5
        </p>
      </div>

      {/* Scenario Input */}
      <Card>
        <CardHeader>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            1. Describe Your Scenario
          </h2>
        </CardHeader>
        <CardBody>
          <form onSubmit={handlePlan} className="space-y-4">
            <TextArea
              label="Scenario"
              rows={4}
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              placeholder="e.g., Meeting with Company X about implementing Topic Y. Need to understand their tech stack, industry trends, and competitive landscape."
              helperText="Describe what you're preparing for and what you need to know"
            />

            <TextArea
              label="Additional Context (Optional)"
              rows={2}
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Any additional details, constraints, or focus areas..."
            />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Input
                label="Max Research Tasks"
                type="number"
                min="1"
                max="10"
                value={maxTasks}
                onChange={(e) => setMaxTasks(parseInt(e.target.value))}
                helperText="1-10 tasks"
              />

              <Select
                label="Planner Model (GPT-5 only)"
                value={plannerModel}
                onChange={(e) => setPlannerModel(e.target.value)}
                options={[
                  { value: 'gpt-5-mini', label: 'GPT-5 Mini (Fast, Recommended)' },
                  { value: 'gpt-5-nano', label: 'GPT-5 Nano (Fastest)' },
                  { value: 'gpt-5', label: 'GPT-5 (Most Thorough)' },
                ]}
              />

              <Select
                label="Research Model"
                value={researchModel}
                onChange={(e) => setResearchModel(e.target.value)}
                options={[
                  { value: 'o4-mini-deep-research', label: 'o4-mini (Faster, Cheaper)' },
                  { value: 'o3-deep-research', label: 'o3 (More Thorough)' },
                ]}
              />
            </div>

            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="enableWebSearch"
                checked={enableWebSearch}
                onChange={(e) => setEnableWebSearch(e.target.checked)}
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
              />
              <label
                htmlFor="enableWebSearch"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Enable web search for research tasks
              </label>
            </div>
          </form>
        </CardBody>
        <CardFooter>
          <div className="flex justify-end">
            <Button
              onClick={handlePlan}
              isLoading={planMutation.isPending}
              disabled={!scenario.trim()}
            >
              Generate Research Plan
            </Button>
          </div>
        </CardFooter>
      </Card>

      {/* Error Display */}
      {planMutation.isError && (
        <Card className="bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
          <CardBody>
            <p className="text-red-800 dark:text-red-300">
              Failed to generate plan: {(planMutation.error as Error).message}
            </p>
          </CardBody>
        </Card>
      )}

      {/* Planned Tasks */}
      {plannedTasks.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                2. Review & Select Research Tasks
              </h2>
              <Button size="sm" variant="ghost" onClick={toggleAll}>
                {selectedTasks.size === plannedTasks.length ? 'Deselect All' : 'Select All'}
              </Button>
            </div>
          </CardHeader>
          <CardBody className="space-y-3">
            {plannedTasks.map((task, idx) => (
              <div
                key={idx}
                className={`p-4 border rounded-lg cursor-pointer transition-all ${
                  selectedTasks.has(idx)
                    ? 'border-primary-600 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                }`}
                onClick={() => toggleTask(idx)}
              >
                <div className="flex items-start space-x-3">
                  <input
                    type="checkbox"
                    checked={selectedTasks.has(idx)}
                    onChange={() => toggleTask(idx)}
                    className="mt-1 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                        {task.title}
                      </h3>
                      {task.estimated_cost && (
                        <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                          ~${task.estimated_cost.toFixed(2)}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {task.prompt}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </CardBody>
          <CardFooter>
            <div className="flex items-center justify-between w-full">
              <div className="space-y-1">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {selectedTasks.size} of {plannedTasks.length} tasks selected
                </p>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">
                  Total Estimated Cost: ${totalCost.toFixed(2)}
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <Select
                  label="Priority"
                  value={priority.toString()}
                  onChange={(e) => setPriority(parseInt(e.target.value))}
                  options={[
                    { value: '1', label: 'High' },
                    { value: '3', label: 'Normal' },
                    { value: '5', label: 'Low' },
                  ]}
                  className="w-32"
                />
                <Button
                  onClick={handleExecute}
                  isLoading={executeMutation.isPending}
                  disabled={selectedTasks.size === 0}
                >
                  Start Research ({selectedTasks.size} {selectedTasks.size === 1 ? 'task' : 'tasks'})
                </Button>
              </div>
            </div>
          </CardFooter>
        </Card>
      )}

      {/* Info Card */}
      {plannedTasks.length === 0 && (
        <Card className="bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
          <CardBody>
            <div className="space-y-2">
              <h3 className="font-semibold text-blue-900 dark:text-blue-300">
                How Prep Research Works
              </h3>
              <ul className="text-sm text-blue-800 dark:text-blue-400 space-y-1 list-disc list-inside">
                <li>
                  <strong>Plan:</strong> GPT-5 models analyze your scenario and generate targeted
                  research tasks
                </li>
                <li>
                  <strong>Review:</strong> Select which research angles are most important
                </li>
                <li>
                  <strong>Execute:</strong> Deep research models (o3/o4-mini) perform comprehensive
                  research
                </li>
                <li>
                  <strong>Results:</strong> All research reports are linked together by batch ID
                </li>
              </ul>
              <p className="text-xs text-blue-700 dark:text-blue-500 mt-3">
                Tip: The planner uses GPT-5 models ONLY (no old models). Research execution uses
                o3 or o4-mini deep research models.
              </p>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
