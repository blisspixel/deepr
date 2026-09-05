import { cn } from '@/lib/utils'

/** The open well shares its geometry with the favicon through one SVG mask. */
export function DeeprMark({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn('deepr-mark inline-block h-7 w-7 shrink-0', className)}
      aria-hidden="true"
      {...props}
    />
  )
}

/** A theme-aware mark with a live, readable wordmark. */
export function DeeprLogo({
  collapsed = false,
  className,
}: {
  collapsed?: boolean
  className?: string
}) {
  return (
    <span className={cn('flex items-center gap-2', className)}>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <DeeprMark className="h-6 w-6" />
      </span>
      {!collapsed && <span className="text-xl font-semibold tracking-tight">Deepr</span>}
    </span>
  )
}
