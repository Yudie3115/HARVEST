import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import SourcePill from './SourcePill'

const mdComponents = {
  p: ({ children }) => (
    <p style={{ margin: '0 0 0.65em', lineHeight: 1.65 }} className="md-last-no-margin">
      {children}
    </p>
  ),
  h1: ({ children }) => (
    <h1 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 17, fontWeight: 600, color: '#e8e4da', margin: '0.8em 0 0.4em', lineHeight: 1.3 }}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 15, fontWeight: 600, color: '#e8e4da', margin: '0.8em 0 0.35em', lineHeight: 1.3 }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: 14, fontWeight: 600, color: '#d4cfc6', margin: '0.7em 0 0.3em', lineHeight: 1.3 }}>{children}</h3>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: '0.3em 0 0.65em', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 3 }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '0.3em 0 0.65em', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 3 }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ lineHeight: 1.6, color: '#d4cfc6' }}>{children}</li>
  ),
  strong: ({ children }) => (
    <strong style={{ color: '#e8e4da', fontWeight: 600 }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ color: '#c9c4bc', fontStyle: 'italic' }}>{children}</em>
  ),
  code: ({ inline, children }) =>
    inline ? (
      <code style={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '0.88em', background: '#1a2218', border: '1px solid #2a3329', borderRadius: 4, padding: '1px 5px', color: '#8ecfaa' }}>
        {children}
      </code>
    ) : (
      <code style={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '0.85em', color: '#8ecfaa' }}>{children}</code>
    ),
  pre: ({ children }) => (
    <pre style={{ background: '#0e1510', border: '1px solid #2a3329', borderRadius: 8, padding: '12px 14px', overflowX: 'auto', margin: '0.5em 0 0.8em', fontSize: '0.85em', lineHeight: 1.6 }}>
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{ borderLeft: '3px solid #3d6b4f', margin: '0.5em 0', paddingLeft: 12, color: '#8a9489', fontStyle: 'italic' }}>
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: '#6ab08a', textDecoration: 'underline', textUnderlineOffset: 3 }}>
      {children}
    </a>
  ),
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid #2a3329', margin: '0.8em 0' }} />,
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', margin: '0.5em 0 0.8em' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th style={{ border: '1px solid #2a3329', padding: '6px 10px', background: '#141a15', color: '#d4a853', textAlign: 'left', fontFamily: '"IBM Plex Mono", monospace', fontSize: 11, fontWeight: 500 }}>
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td style={{ border: '1px solid #2a3329', padding: '6px 10px', color: '#d4cfc6', verticalAlign: 'top' }}>{children}</td>
  ),
}

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
