import { memo, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'

import { cn } from '@/lib/utils'

interface AssistantTextProps {
  text: string
  isStreaming: boolean
  className?: string
}

function AssistantTextImpl({ text, isStreaming, className }: AssistantTextProps) {
  const markdown = useMemo(
    () => (
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
        {text}
      </ReactMarkdown>
    ),
    [text],
  )

  return (
    <div
      className={cn(
        'markdown-body min-w-0 break-words',
        isStreaming && 'streaming-caret',
        className,
      )}
    >
      {markdown}
    </div>
  )
}

export const AssistantText = memo(AssistantTextImpl)
