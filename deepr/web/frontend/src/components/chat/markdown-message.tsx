import { useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeSanitize from 'rehype-sanitize'
import rehypeKatex from 'rehype-katex'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Check, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'

function CodeBlock({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {
      // Clipboard API not available (e.g. non-HTTPS)
    })
  }, [children])

  return (
    <div className="relative group/code">
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-background/80 opacity-0 group-hover/code:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
        aria-label="Copy code"
      >
        {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
      <SyntaxHighlighter
        style={oneDark}
        language={language}
        PreTag="div"
        customStyle={{ margin: 0, borderRadius: '0.375rem', fontSize: '0.8125rem' }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  )
}

interface MarkdownMessageProps {
  content: string
  className?: string
}

export function MarkdownMessage({ content, className }: MarkdownMessageProps) {
  return (
    <div className={cn(
      'prose prose-sm dark:prose-invert max-w-none',
      'prose-headings:text-foreground prose-p:text-foreground/90',
      'prose-a:text-primary prose-strong:text-foreground',
      'prose-code:text-foreground prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded',
      'prose-pre:bg-transparent prose-pre:p-0',
      className,
    )}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeSanitize, rehypeKatex]}
        components={{
          code({ className: codeClassName, children, ...props }) {
            const match = /language-(\w+)/.exec(codeClassName || '')
            const codeString = String(children).replace(/\n$/, '')

            if (match) {
              return <CodeBlock language={match[1]}>{codeString}</CodeBlock>
            }

            return (
              <code className={codeClassName} {...props}>
                {children}
              </code>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
