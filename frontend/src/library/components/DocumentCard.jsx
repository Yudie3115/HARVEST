import { Link } from 'react-router-dom'

const SUMMARY_MAX_CHARS = 200

function truncate(text, max) {
  if (!text) return ''
  if (text.length <= max) return text
  return `${text.slice(0, max).trimEnd()}…`
}

function Tag({ children }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 8px',
        borderRadius: 999,
        border: '1px solid #2a3329',
        background: '#0f1a12',
        color: '#8a9489',
        fontSize: 11,
        fontFamily: '"IBM Plex Mono", monospace',
      }}
    >
      {children}
    </span>
  )
}

// Non-interactive card: topic/crop/region tags here are display-only labels,
// not clickable filters — clicking anywhere on the card opens the detail page.
export default function DocumentCard({ doc }) {
  const tags = [...(doc.topics || []), ...(doc.crops || []), ...(doc.regions || [])]

  return (
    <Link
      to={`/documents/${doc.id}`}
      style={{
        display: 'block',
        padding: '16px 18px',
        borderRadius: 10,
        border: '1px solid #2a3329',
        background: '#141a15',
        textDecoration: 'none',
        color: 'inherit',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#3d6b4f'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#2a3329'
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 6,
        }}
      >
        <h2
          style={{
            fontFamily: 'Fraunces, Georgia, serif',
            fontSize: 17,
            fontWeight: 600,
            color: '#e8e4da',
            margin: 0,
            lineHeight: 1.3,
          }}
        >
          {doc.title}
        </h2>
        {doc.document_category && (
          <span
            style={{
              flexShrink: 0,
              padding: '3px 9px',
              borderRadius: 999,
              border: '1px solid #d4a853',
              color: '#d4a853',
              fontSize: 11,
              fontFamily: '"IBM Plex Mono", monospace',
              whiteSpace: 'nowrap',
            }}
          >
            {doc.document_category}
          </span>
        )}
      </div>

      {doc.summary && (
        <p style={{ color: '#d4cfc6', fontSize: 14, lineHeight: 1.55, margin: '0 0 10px' }}>
          {truncate(doc.summary, SUMMARY_MAX_CHARS)}
        </p>
      )}

      {tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {tags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </div>
      )}
    </Link>
  )
}
