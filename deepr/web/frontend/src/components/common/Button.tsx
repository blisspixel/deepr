import { ButtonHTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  children: ReactNode
  isLoading?: boolean
}

export default function Button({
  variant = 'primary',
  size = 'md',
  children,
  isLoading = false,
  disabled,
  className,
  ...props
}: ButtonProps) {
  const baseStyles = clsx(
    'inline-flex items-center justify-center font-medium rounded-lg',
    'transition-all duration-150 ease-out',
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
    'disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none'
  )

  const sizes = {
    sm: 'px-3 py-1.5 text-xs gap-1.5',
    md: 'px-4 py-2 text-sm gap-2',
    lg: 'px-6 py-3 text-base gap-2',
  }

  const variantStyles: Record<string, string> = {
    primary: clsx(
      'bg-[var(--color-accent)] text-white',
      'hover:bg-[var(--color-accent-hover)] hover:shadow-md',
      'active:scale-[0.98]',
      'focus-visible:ring-[var(--color-accent)]'
    ),
    secondary: clsx(
      'bg-[var(--color-surface)] text-[var(--color-text-primary)]',
      'border border-[var(--color-border)]',
      'hover:bg-[var(--color-surface-hover)] hover:border-[var(--color-border-hover)]',
      'active:scale-[0.98]',
      'focus-visible:ring-[var(--color-border)]'
    ),
    ghost: clsx(
      'text-[var(--color-text-secondary)]',
      'hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]',
      'active:scale-[0.98]',
      'focus-visible:ring-[var(--color-border)]'
    ),
    danger: clsx(
      'bg-[var(--color-error)] text-white',
      'hover:bg-[var(--color-error)]/90 hover:shadow-md',
      'active:scale-[0.98]',
      'focus-visible:ring-[var(--color-error)]'
    ),
  }

  return (
    <button
      className={clsx(baseStyles, sizes[size], variantStyles[variant], className)}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading && (
        <svg
          className="animate-spin h-4 w-4"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      )}
      {isLoading ? 'Loading...' : children}
    </button>
  )
}
