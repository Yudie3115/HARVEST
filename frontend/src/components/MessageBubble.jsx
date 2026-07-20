import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import SourcePill from './SourcePill'
import { mdComponents } from '../lib/markdownComponents'

export default function MessageBubble({ message, onShowSources }) {
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
    <div className="msg-enter" style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      <div
        style={{
          flexShrink: 0,
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: '#1e3a28',
          border: '1px solid #3d6b4f',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 14,
          marginTop: 2,
        }}
      >
        🌾
      </div>
      <div style={{ flex: 1, maxWidth: 'calc(100% - 38px)' }}>
        <div
          style={{
            padding: '11px 16px',
            borderRadius: '4px 16px 16px 16px',
            background: message.isError ? '#1f1414' : message.noResults ? '#161a16' : '#191f1a',
            border: `1px solid ${message.isError ? '#3d2020' : message.noResults ? '#202820' : '#252e25'}`,
            color: message.isError ? '#c97d7d' : message.noResults ? '#6a7a6a' : '#d4cfc6',
            fontSize: 15,
            lineHeight: 1.6,
            fontFamily: 'Outfit, system-ui, sans-serif',
          }}
        >
          {message.isError ? (
            message.content
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>
        <SourcePill sources={message.sources} onOpen={onShowSources} />
      </div>
    </div>
  )
}
