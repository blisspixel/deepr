import { useQuery } from '@tanstack/react-query'
import { BookOpen, Lightbulb, Loader2 } from 'lucide-react'
import { expertsApi } from '@/api/experts'
import { expertSourceUrl, expertStudyDate, type ExpertPosition, type ExpertSource, type ExpertStudy } from '@/lib/expert-perspective'
import EmptyState from '@/components/shared/empty-state'
import PartialQueryError from '@/components/shared/partial-query-error'

function SourceLink({ source }: { source: ExpertSource }) {
  const url = expertSourceUrl(source.url)
  return url
    ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 break-words">{source.title || url}</a>
    : <span className="break-words">{source.title || 'Retained source'}</span>
}

function Position({ position, study, sources }: { position: ExpertPosition; study?: ExpertStudy | null; sources?: ExpertSource[] | null }) {
  return (
    <article className="min-w-0 rounded-xl border bg-card p-5 space-y-3">
      <h3 className="text-base font-semibold leading-snug">{position.question || 'Recorded position'}</h3>
      <p className="text-sm leading-relaxed">{position.stance || 'No stance recorded.'}</p>
      <div className="border-l-2 border-primary/30 pl-3 text-sm leading-relaxed">
        <p className="font-medium mb-1">Why</p>
        <p className="text-muted-foreground">{position.reasoning || 'The reasoning behind this position has not been recorded.'}</p>
      </div>
      {position.unresolved_dissent && <p className="text-sm leading-relaxed"><span className="font-medium">Unresolved: </span>{position.unresolved_dissent}</p>}
      <details className="text-sm">
        <summary className="cursor-pointer rounded font-medium text-primary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">Evidence and conditions for revision</summary>
        <div className="mt-3 space-y-3 text-muted-foreground">
          <p><span className="font-medium text-foreground">What would change this view: </span>{position.would_change_my_mind || 'No revision condition recorded.'}</p>
          {position.confidence_basis && <p><span className="font-medium text-foreground">Basis: </span>{position.confidence_basis}</p>}
          {!position.supported_by.length && <p>No supporting findings are linked to this position.</p>}
          {position.supported_by.map((id) => {
            const finding = study?.findings.find((item) => item.finding_id === id)
            return (
              <div key={id} className="rounded-lg border p-3 space-y-2">
                <p className="font-medium text-foreground">{finding?.title || `Finding ${id} is not available in this study.`}</p>
                {finding && !finding.is_grounded && <p>A matching source passage has not been verified.</p>}
                {finding?.anchors.map((anchor, index) => <blockquote key={index} className="border-l pl-3 leading-relaxed">{anchor}</blockquote>)}
                {finding?.corpus_shas.map((sha) => {
                  const source = sources?.find((item) => item.sha256 === sha)
                  return <div key={sha}>{source ? <SourceLink source={source} /> : 'Retained source metadata is unavailable.'}</div>
                })}
              </div>
            )
          })}
        </div>
      </details>
    </article>
  )
}

export function ExpertPerspective({ name }: { name: string }) {
  const encodedName = encodeURIComponent(name)
  const perspective = useQuery({ queryKey: ['experts', name, 'perspective'], queryFn: () => expertsApi.getPerspective(encodedName), retry: false })
  const study = useQuery({ queryKey: ['experts', name, 'study'], queryFn: () => expertsApi.getStudy(encodedName), retry: false })
  const sources = useQuery({ queryKey: ['experts', name, 'sources'], queryFn: () => expertsApi.getSources(encodedName), retry: false })
  const brief = perspective.data
  const studyDate = expertStudyDate(study.data?.started_at || '')

  return (
    <div className="p-4 sm:p-6 space-y-6 break-words">
      {perspective.isError && <PartialQueryError title="Perspective unavailable" description="The retained perspective could not be loaded. Any previously loaded perspective below may be out of date." onRetry={() => void perspective.refetch()} retrying={perspective.isFetching} />}
      {study.isError && <PartialQueryError title="Study unavailable" description="Supporting findings and the study date could not be loaded." onRetry={() => void study.refetch()} retrying={study.isFetching} />}
      {sources.isError && <PartialQueryError title="Sources unavailable" description="The retained source inventory could not be loaded." onRetry={() => void sources.refetch()} retrying={sources.isFetching} />}
      {perspective.isPending ? (
        <div role="status" className="flex items-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading perspective</div>
      ) : !brief && !perspective.isError ? (
        <EmptyState icon={BookOpen} title="No perspective recorded yet" description="This expert needs retained research, study, and a briefing before it can show reasoned positions. A profile name alone does not establish expertise." />
      ) : null}
      {brief && <>
        <section aria-label="Expert perspective" className="rounded-xl border bg-primary/5 p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold flex items-center gap-2"><Lightbulb className="w-5 h-5 text-primary" />Perspective</h2>
            <span className="text-xs text-muted-foreground">{studyDate ? `Study started ${studyDate} (UTC)` : 'Study date unavailable'}</span>
          </div>
          <p className="text-sm leading-relaxed max-w-5xl">{brief.orientation || 'No orientation recorded.'}</p>
          <p className="text-xs leading-relaxed text-muted-foreground">Based on stored research. Updates relevant to your question have not been checked by opening this profile.</p>
        </section>
        <section aria-label="Reasoned positions" className="space-y-3">
          <h2 className="text-sm font-semibold">Positions and reasoning</h2>
          {brief.positions.length ? <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {brief.positions.map((position, index) => <Position key={index} position={position} study={study.data} sources={sources.data} />)}
          </div> : <p className="text-sm text-muted-foreground">This briefing contains no positions.</p>}
        </section>
        {!!brief.anticipated_questions.length && <section className="space-y-3" aria-label="Questions this expert has considered">
          <h2 className="text-sm font-semibold">Questions considered</h2>
          {brief.anticipated_questions.map((question, index) => <details key={index} className="rounded-lg border p-4 text-sm">
            <summary className="cursor-pointer font-medium rounded focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">{question.question}</summary>
            <p className="mt-3 text-muted-foreground leading-relaxed">{question.answer}</p>
          </details>)}
        </section>}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {([['Live questions', brief.state.live], ['Still unknown', brief.state.unknown]] as const).map(([title, items]) => <section key={title} className="rounded-xl border p-5 space-y-3">
            <h2 className="text-sm font-semibold">{title}</h2>
            {items.length ? <ul className="list-disc pl-4 space-y-2 text-sm text-muted-foreground">{items.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p className="text-sm text-muted-foreground">None recorded in this briefing. This does not establish complete coverage.</p>}
          </section>)}
        </div>
        {(brief.limitations.length > 0 || (study.data?.limitations.length ?? 0) > 0) && <section className="rounded-xl border p-5 space-y-3">
          <h2 className="text-sm font-semibold">Research limitations</h2>
          <ul className="list-disc pl-4 space-y-2 text-sm text-muted-foreground">{[...new Set([...brief.limitations, ...(study.data?.limitations ?? [])])].map((item, index) => <li key={index}>{item}</li>)}</ul>
        </section>}
      </>}
      {sources.data && <section className="rounded-xl border p-5 space-y-3" aria-label="Retained research">
        <h2 className="text-sm font-semibold">Retained research</h2>
        <p className="text-xs text-muted-foreground">Source availability does not by itself establish coverage or independent corroboration.</p>
        <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-sm">{sources.data.map((source) => <li key={source.sha256}><SourceLink source={source} /></li>)}</ul>
      </section>}
    </div>
  )
}
