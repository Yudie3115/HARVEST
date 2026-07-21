import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Header from '../../components/Header'
import { getDocumentDetail } from '../../api'

// Minimal, unstyled-but-functional detail page. Task 3 rebuilds this with the
// full content spec (excerpts, badges, sanitized links) — this version only
// proves the data path end-to-end, including the not-found state.
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
        // Every non-2xx (404 unpublished/missing/unprocessed, 422 malformed id) is
        // treated the same way at this stage — Task 3 refines the messaging.
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
          padding: '24px 16px',
          color: '#e8e4da',
          fontFamily: 'Outfit, system-ui, sans-serif',
        }}
      >
        {loading && <p style={{ color: '#8a9489' }}>Loading…</p>}

        {!loading && notFound && (
          <p style={{ color: '#d4a853' }}>Document not found.</p>
        )}

        {!loading && !notFound && document && (
          <>
            <h1 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 24, marginBottom: 12 }}>
              {document.title}
            </h1>
            <p style={{ color: '#d4cfc6' }}>{document.summary}</p>
          </>
        )}

        <p style={{ marginTop: 24 }}>
          <Link to="/documents" style={{ color: '#8ecfaa' }}>
            Back to Documents
          </Link>
        </p>
      </div>
    </div>
  )
}
