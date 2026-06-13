import { useState, type ComponentType } from 'react'
import { Users } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ExpertPortraitProps {
  name: string
  portraitUrl?: string | null
  /** Size/shape classes applied to both the image and the fallback box. */
  className?: string
  /** Classes for the fallback icon (size, and color via tailwind-merge). */
  iconClassName?: string
  /** Fallback icon when there is no portrait or it fails to load. */
  FallbackIcon?: ComponentType<{ className?: string }>
  /** Background classes for the fallback box. */
  fallbackClassName?: string
}

/**
 * Expert portrait that never renders a broken image.
 *
 * Shows the generated portrait when present, and falls back to an icon box
 * both when no portrait URL is set AND when the URL fails to load (onError) -
 * the latter case is what previously left broken-image icons on the expert
 * pages. One component so every portrait site degrades consistently.
 */
export function ExpertPortrait({
  name,
  portraitUrl,
  className,
  iconClassName,
  FallbackIcon = Users,
  fallbackClassName = 'bg-primary/10',
}: ExpertPortraitProps) {
  const [failed, setFailed] = useState(false)

  if (portraitUrl && !failed) {
    return (
      <img
        src={portraitUrl}
        alt={`${name} portrait`}
        className={cn('object-cover', className)}
        onError={() => setFailed(true)}
      />
    )
  }

  return (
    <div className={cn('flex items-center justify-center', fallbackClassName, className)}>
      <FallbackIcon className={cn('text-primary', iconClassName)} />
    </div>
  )
}
