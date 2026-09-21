import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { expertsApi } from '@/api/experts'
import { Button } from '@/components/ui/button'
import PartialQueryError from '@/components/shared/partial-query-error'

export function ExpertFormation({ name, hasPerspective }: { name: string; hasPerspective: boolean }) {
  const client = useQueryClient()
  const encodedName = encodeURIComponent(name)
  const [pollUntil, setPollUntil] = useState(0)
  const formation = useQuery({
    queryKey: ['experts', name, 'formation'], queryFn: () => expertsApi.getFormation(encodedName), retry: false,
    refetchInterval: query => Date.now() < pollUntil || query.state.data?.status === 'running' ||
      (query.state.data === null && !hasPerspective && query.state.dataUpdateCount < 15) ? 2000 : false,
  })
  const build = useMutation({
    mutationFn: () => expertsApi.build(encodedName),
    onSuccess: () => {
      setPollUntil(Date.now() + 30000)
      return client.invalidateQueries({ queryKey: ['experts', name, 'formation'] })
    },
  })
  const status = formation.data?.status
  useEffect(() => {
    if (status === 'research_complete') {
      for (const key of ['perspective', 'study', 'sources']) void client.invalidateQueries({ queryKey: ['experts', name, key] })
    }
  }, [status, name, client])
  if (formation.isError) return <PartialQueryError title="Build status unavailable" description="The research build record could not be loaded." onRetry={() => void formation.refetch()} retrying={formation.isFetching} />
  if (formation.isPending || (!formation.data && hasPerspective)) return null
  const running = status === 'running'
  const complete = status === 'research_complete'
  return <section className="rounded-xl border p-5 space-y-3" aria-label="Expert research build">
    <h2 className="text-sm font-semibold">{running ? 'Developing knowledge' : complete ? 'Research foundation built' : 'Build research and knowledge'}</h2>
    <p className="text-sm text-muted-foreground" role="status">{formation.data?.progress || 'Research sources, study how the subject works, form reasoned positions, and build a linked knowledge notebook.'}</p>
    {formation.data && <p className="text-xs text-muted-foreground">Stage: {formation.data.stage}. Local model calls: {formation.data.model_calls}. External API cost: $0.</p>}
    <p className="text-xs text-muted-foreground">Practical guidance and currentness require review. A completed build does not certify expertise.</p>
    {!running && !hasPerspective && <Button onClick={() => build.mutate()} disabled={build.isPending} loading={build.isPending}>{formation.data ? 'Retry local build' : 'Build with local capacity'}</Button>}
    {build.isError && <p role="alert" className="text-sm text-destructive">{build.error.message}</p>}
    {!!formation.data?.limitations.length && <details className="text-sm"><summary className="cursor-pointer">Research limitations</summary><ul className="list-disc pl-5 mt-2 space-y-1">{formation.data.limitations.map((note, index) => <li key={index}>{note}</li>)}</ul></details>}
  </section>
}
