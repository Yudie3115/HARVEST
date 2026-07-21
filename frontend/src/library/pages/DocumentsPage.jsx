import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../components/Header'
import { getDocuments } from '../../api'

// Minimal, unstyled-but-functional list page. Task 2 rebuilds this with facets,
// search, and pagination — this version only proves the data path end-to-end.
export default function DocumentsPage() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getDocuments()
      .then((data) => {
        if (!cancelled) setDocuments(data.items || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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
        <h1 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 24, marginBottom: 16 }}>
          Documents
        </h1>

        {loading && <p style={{ color: '#8a9489' }}>Loading documents…</p>}
        {error && <p style={{ color: '#d4a853' }}>Failed to load documents. Please try again.</p>}

        {!loading && !error && (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {documents.map((doc) => (
              <li key={doc.id}>
                <Link to={`/documents/${doc.id}`} style={{ color: '#8ecfaa', textDecoration: 'underline' }}>
                  {doc.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
