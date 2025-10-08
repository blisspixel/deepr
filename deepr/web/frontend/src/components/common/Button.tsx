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
  const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed'

  const sizes = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  }

  const getVariantStyle = () => {
    if (variant === 'primary') {
      return {
        backgroundColor: 'var(--color-text-primary)',
        color: 'var(--color-bg)'
      }
    }
    if (variant === 'secondary') {
      return {
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text-primary)'
      }
    }
    return { color: 'var(--color-text-secondary)' }
  }

  return (
    <button
      className={clsx(baseStyles, sizes[size], className)}
      style={getVariantStyle()}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? 'Loading...' : children}
    </button>
  )
}
