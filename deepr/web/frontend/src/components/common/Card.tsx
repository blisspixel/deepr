import { ReactNode } from 'react'
import clsx from 'clsx'

interface CardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  hoverable?: boolean
}

export default function Card({ children, className, onClick, hoverable = false }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-2xl',
        onClick && 'cursor-pointer',
        className
      )}
      style={{
        backgroundColor: 'var(--color-surface)',
      }}
      onClick={onClick}
    >
      {children}
    </div>
  )
}

interface CardHeaderProps {
  children: ReactNode
  className?: string
}

export function CardHeader({ children, className }: CardHeaderProps) {
  return (
    <div className={clsx('px-6 py-4', className)}>
      {children}
    </div>
  )
}

interface CardBodyProps {
  children: ReactNode
  className?: string
}

export function CardBody({ children, className }: CardBodyProps) {
  return <div className={clsx('px-6 py-5', className)}>{children}</div>
}

interface CardFooterProps {
  children: ReactNode
  className?: string
}

export function CardFooter({ children, className }: CardFooterProps) {
  return (
    <div className={clsx('px-6 py-4', className)}>
      {children}
    </div>
  )
}
