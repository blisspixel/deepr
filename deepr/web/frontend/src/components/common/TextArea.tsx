import { TextareaHTMLAttributes, forwardRef } from 'react'
import clsx from 'clsx'

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
}

const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  ({ label, error, className, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-xs font-medium mb-2" style={{ color: 'var(--color-text-secondary)' }}>
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          className={clsx(
            'w-full px-4 py-3 rounded-lg focus:outline-none resize-none',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            className
          )}
          style={{
            backgroundColor: 'var(--color-bg)',
            color: 'var(--color-text-primary)',
            border: 'none'
          }}
          {...props}
        />
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </div>
    )
  }
)

TextArea.displayName = 'TextArea'

export default TextArea
