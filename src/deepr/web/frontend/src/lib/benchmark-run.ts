export type BenchmarkTier = 'all' | 'chat' | 'news' | 'research' | 'docs'

export type BenchmarkRunOptions = {
  tier: BenchmarkTier
  quick: boolean
  no_judge: boolean
}

export type BenchmarkEstimate = {
  estimated_cost: number
  model_count: number
  provider_count: number
  tier: string
}

export type BenchmarkEstimateSnapshot = BenchmarkEstimate & {
  options: BenchmarkRunOptions
}

export type BenchmarkStartOptions = BenchmarkRunOptions & {
  max_estimated_cost: number
}

export function snapshotBenchmarkEstimate(
  estimate: BenchmarkEstimate,
  options: BenchmarkRunOptions,
): BenchmarkEstimateSnapshot {
  return { ...estimate, options: { ...options } }
}

export function benchmarkOptionsMatch(
  left: BenchmarkRunOptions,
  right: BenchmarkRunOptions,
): boolean {
  return left.tier === right.tier
    && left.quick === right.quick
    && left.no_judge === right.no_judge
}

export function verifiedProviderKeys(
  keys: Record<string, boolean> | undefined,
  queryFailed: boolean,
): Record<string, boolean> | undefined {
  return queryFailed ? undefined : keys
}

export function registryFailureBlocksSurface(
  registryError: boolean,
  hasRegistryData: boolean,
  hasBenchmarkResult: boolean,
): boolean {
  return registryError && !hasRegistryData && !hasBenchmarkResult
}

export function confirmedBenchmarkOptions(
  estimate: BenchmarkEstimateSnapshot,
  currentOptions: BenchmarkRunOptions,
): BenchmarkStartOptions | null {
  return benchmarkOptionsMatch(estimate.options, currentOptions)
    ? { ...estimate.options, max_estimated_cost: estimate.estimated_cost }
    : null
}
