import { cn } from '@/lib/utils'

/**
 * Deepr brand mark - rune-inspired, drawn from Kenaz (Elder Futhark): the rune
 * of the torch, the beacon, knowledge and expertise. This is an interpretation,
 * not a literal glyph: the angular chevron is the rune body / torch, and the
 * short rays read as torchlight - illumination, the "aha" of research.
 *
 * Pure strokes in `currentColor` so it works in light mode, dark mode, and as a
 * flat monochrome favicon. Tint it by setting text color (e.g. text-primary,
 * or text-primary-foreground inside an accent badge).
 */
export function DeeprMark({
  className,
  withRays = true,
  ...props
}: React.SVGProps<SVGSVGElement> & { withRays?: boolean }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('h-7 w-7', className)}
      aria-hidden="true"
      {...props}
    >
      {/* Kenaz - the torch / beacon. Angular chevron, apex to the right. */}
      <path
        d="M12 4.5 L22.5 16 L12 27.5"
        stroke="currentColor"
        strokeWidth={3.25}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Torchlight - illumination radiating from the beacon's point. */}
      {withRays && (
        <path
          d="M24.5 16 H29 M22.5 9.5 L26.5 5.5 M22.5 22.5 L26.5 26.5"
          stroke="currentColor"
          strokeWidth={2.25}
          strokeLinecap="round"
          opacity={0.55}
        />
      )}
    </svg>
  )
}

/**
 * Full lockup: the mark in an accent badge plus the "Deepr" wordmark. The badge
 * uses the theme's primary token, so it tracks the user's chosen accent color
 * and adapts to light/dark automatically.
 */
export function DeeprLogo({
  collapsed = false,
  className,
}: {
  collapsed?: boolean
  className?: string
}) {
  return (
    <span className={cn('flex items-center gap-2', className)}>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
        <DeeprMark className="h-[19px] w-[19px]" />
      </span>
      {!collapsed && <span className="text-lg font-semibold tracking-tight">Deepr</span>}
    </span>
  )
}
