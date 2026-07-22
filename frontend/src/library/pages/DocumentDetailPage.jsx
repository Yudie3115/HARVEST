import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Header from '../../components/Header'
import Pill from '../components/Pill'
import { getDocumentDetail } from '../../api'
import { mdComponents } from '../../lib/markdownComponents'
import { isSafeUrl } from '../../lib/sanitize'

// Full detail view. Every non-2xx response from getDocumentDetail (404 for
// missing/unpublished/unprocessed/below-threshold documents, 422 for a
// malformed :id) is treated identically here — the backend guarantees these
// are byte-identical responses, so the frontend must not try to distinguish
// them or infer why a document isn't available.
export default function DocumentDetailPage() {
  const { id } = useParams()
  const [document, setDocument] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setNotFound(false)
    setDocument(null)
    getDocumentDetail(id)
      .then((data) => {
        if (!cancelled) setDocument(data)
      })
      .catch(() => {
        if (!cancelled) setNotFound(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100dvh',
        background: '#111613',
        overflow: 'hidden',
      }}
    >
      <Header />
      <div
        style={{
          height: '100%',
          overflowY: 'auto',
          padding: '24px 16px 48px',
          color: '#e8e4da',
          fontFamily: 'Outfit, system-ui, sans-serif',
        }}
      >
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          {loading && <p style={{ color: '#8a9489' }}>Loading…</p>}

          {!loading && notFound && <NotFoundState />}

          {!loading && !notFound && document && <DocumentDetail doc={document} />}
        </div>
      </div>
    </div>
  )
}

function NotFoundState() {
  return (
    <div
      style={{
        padding: '28px 20px',
        borderRadius: 10,
        border: '1px solid #2a3329',
        background: '#141a15',
        textAlign: 'center',
      }}
    >
      <p style={{ color: '#d4cfc6', margin: '0 0 14px' }}>
        This document isn&apos;t available. It may have been removed or isn&apos;t public.
      </p>
      <Link to="/documents" style={{ color: '#8ecfaa' }}>
        Back to Documents
      </Link>
    </div>
  )
}

function DocumentDetail({ doc }) {
  const tags = [...(doc.topics || []), ...(doc.crops || []), ...(doc.regions || [])]
  const hasKeyPractices = Array.isArray(doc.key_practices) && doc.key_practices.length > 0
  const hasExcerpts = Array.isArray(doc.excerpts) && doc.excerpts.length > 0
  const sourceIsSafe = isSafeUrl(doc.source_url)

  return (
    <>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 10,
        }}
      >
        <h1
          style={{
            fontFamily: 'Fraunces, Georgia, serif',
            fontSize: 26,
            fontWeight: 600,
            color: '#e8e4da',
            margin: 0,
            lineHeight: 1.3,
          }}
        >
          {doc.title}
        </h1>
        {doc.document_category && <Pill variant="gold">{doc.document_category}</Pill>}
      </div>

      {tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
          {tags.map((tag) => (
            <Pill key={tag}>{tag}</Pill>
          ))}
        </div>
      )}

      {doc.summary && (
        <div style={{ marginBottom: hasKeyPractices ? 24 : 0 }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {doc.summary}
          </ReactMarkdown>
        </div>
      )}

      {hasKeyPractices && (
        <div style={{ marginBottom: 24 }}>
          <SectionLabel>Key practices</SectionLabel>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {doc.key_practices.map((practice, i) => (
              <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ color: '#8ecfaa', fontSize: 14, lineHeight: 1.6, flexShrink: 0 }} aria-hidden="true">
                  ✓
                </span>
                <span style={{ color: '#d4cfc6', fontSize: 14, lineHeight: 1.6 }}>{practice}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(doc.actionable || doc.has_data) && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {doc.actionable && <Pill variant="green">Actionable</Pill>}
          {doc.has_data && <Pill variant="green">Has data</Pill>}
        </div>
      )}

      {hasExcerpts && (
        <div style={{ marginBottom: 24 }}>
          <SectionLabel>Excerpts</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {doc.excerpts.map((excerpt) => (
              <div
                key={excerpt.chunk_index}
                style={{
                  padding: '10px 14px',
                  borderLeft: '3px solid #3d6b4f',
                  background: '#0f1a12',
                  color: '#c9c4bc',
                  fontFamily: '"IBM Plex Mono", monospace',
                  fontSize: 12.5,
                  lineHeight: 1.7,
                }}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                  {excerpt.text}
                </ReactMarkdown>
              </div>
            ))}
          </div>
        </div>
      )}

      {doc.source_url && (
        <div style={{ marginBottom: 24 }}>
          <SectionLabel>Source</SectionLabel>
          {sourceIsSafe ? (
            <a
              href={doc.source_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#6ab08a', textDecoration: 'underline', textUnderlineOffset: 3, fontSize: 14 }}
            >
              View original source
            </a>
          ) : (
            <span style={{ color: '#8a9489', fontSize: 14 }}>{doc.source_url}</span>
          )}
        </div>
      )}

      <p style={{ marginTop: 32 }}>
        <Link to="/documents" style={{ color: '#8ecfaa', fontSize: 14 }}>
          ← Back to Documents
        </Link>
      </p>
    </>
  )
}

function SectionLabel({ children }) {
  return (
    <div
      style={{
        fontFamily: '"IBM Plex Mono", monospace',
        fontSize: 11,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: '#8a9489',
        marginBottom: 8,
      }}
    >
      {children}
    </div>
  )
}
