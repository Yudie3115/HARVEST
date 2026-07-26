import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sprout } from 'lucide-react'
import SourcePill from './SourcePill'
import ResearchProgress from './ResearchProgress'
import SuggestedQuestions from './SuggestedQuestions'
import { mdComponents } from '../lib/markdownComponents'

export default function MessageBubble({
  message,
  onShowSources,
  onAskQuestion,
  interactionsDisabled,
}) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="msg-enter" style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <div
          style={{
            maxWidth: '78%',
            padding: '11px 16px',
            borderRadius: '16px 4px 16px 16px',
            background: '#1a3628',
            color: '#e8e4da',
            fontSize: 15,
            lineHeight: 1.55,
            fontFamily: 'Outfit, system-ui, sans-serif',
          }}
        >
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <article className="msg-enter assistant-response">
      <div className="assistant-response__rail" aria-hidden="true">
        <span className="assistant-response__mark">
          <Sprout size={15} strokeWidth={1.7} />
        </span>
      </div>
      <div className="assistant-response__body">
        <div className="assistant-response__meta">
          <span>Knowledge synthesis</span>
          {message.sources?.length > 0 && (
            <span>{message.sources.length} research reference{message.sources.length === 1 ? '' : 's'}</span>
          )}
        </div>
        <div
          className={`assistant-response__content ${
            message.isError ? 'assistant-response__content--error' : ''
          } ${message.noResults ? 'assistant-response__content--empty' : ''}`}
        >
          {message.isStreaming && !message.content ? (
            <ResearchProgress
              stage={message.researchStage}
              sourceCount={message.researchSourceCount}
            />
          ) : message.isError ? (
            message.content
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>
        {message.isStreaming && message.content && (
          <ResearchProgress
            compact
            stage={message.researchStage || 'synthesizing'}
            sourceCount={message.researchSourceCount}
          />
        )}
        <SourcePill sources={message.sources} onOpen={onShowSources} />
        <SuggestedQuestions
          questions={message.suggestedQuestions}
          onAsk={onAskQuestion}
          disabled={interactionsDisabled}
        />
      </div>
    </article>
  )
}
