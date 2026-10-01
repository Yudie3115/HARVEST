import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Header from '../../components/Header'
import FacetPills from '../components/FacetPills'
import DocumentCard from '../components/DocumentCard'
import Pagination from '../components/Pagination'
import { getDocuments, getFacets } from '../../api'

const LIMIT = 20
const SEARCH_DEBOUNCE_MS = 300

export default function DocumentsPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const topic = searchParams.get('topic') || ''
  const crop = searchParams.get('crop') || ''
  const region = searchParams.get('region') || ''
  const q = searchParams.get('q') || ''
  const offset = Number.parseInt(searchParams.get('offset') || '0', 10) || 0

  const [facets, setFacets] = useState(null)
  const [facetsError, setFacetsError] = useState(false)

  const [documents, setDocuments] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [initialLoad, setInitialLoad] = useState(true)
  const [error, setError] = useState(null)

  // Local, per-keystroke value for the search box. Kept separate from the URL's
  // `q` param so typing doesn't refetch on every character — it's synced to the
  // URL (debounced) below, and synced back from the URL when it changes for any
  // other reason (Clear filters, browser back/forward).
  const [qInput, setQInput] = useState(q)
  const pushedQRef = useRef(q)

  useEffect(() => {
    getFacets()
      .then(setFacets)
      .catch(() => setFacetsError(true))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getDocuments({ topic, crop, region, q, offset, limit: LIMIT })
      .then((data) => {
        if (cancelled) return
        setDocuments(data.items || [])
        setTotal(data.total || 0)
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
          setInitialLoad(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [topic, crop, region, q, offset])

  // Sync qInput from the URL whenever the URL's q changes for a reason other
  // than our own debounced push below (e.g. Clear filters, back/forward nav).
  useEffect(() => {
    if (q !== pushedQRef.current) {
      pushedQRef.current = q
      setQInput(q)
    }
  }, [q])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (qInput === q) return
      pushedQRef.current = qInput
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (qInput) next.set('q', qInput)
        else next.delete('q')
        next.delete('offset')
        return next
      })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput])

  const toggleFacet = (param, value) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (next.get(param) === value) next.delete(param)
      else next.set(param, value)
      next.delete('offset')
      return next
    })
  }

  const clearFilters = () => {
    pushedQRef.current = ''
    setQInput('')
    setSearchParams(new URLSearchParams())
  }

  const handlePageChange = (newOffset) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('offset', String(newOffset))
      return next
    })
  }

  const hasActiveFilters = Boolean(topic || crop || region || q)
  const showEmptyState = !loading && !error && documents.length === 0

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
        <div style={{ maxWidth: 780, margin: '0 auto' }}>
          <h1 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 26, margin: '0 0 6px' }}>
            Documents
          </h1>
          <p style={{ color: '#8a9489', fontSize: 14, margin: '0 0 20px' }}>
            Browse published pre-harvest and post-harvest knowledge documents.
          </p>

          <input
            type="text"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="Search titles and summaries…"
            aria-label="Search documents"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '10px 14px',
              borderRadius: 8,
              border: '1px solid #2a3329',
              background: '#0f1a12',
              color: '#e8e4da',
              fontFamily: 'Outfit, system-ui, sans-serif',
              fontSize: 14,
              marginBottom: 20,
              outline: 'none',
            }}
          />

          {facetsError && (
            <p style={{ color: '#8a9489', fontSize: 13, marginBottom: 16 }}>
              Filters are unavailable right now.
            </p>
          )}
          <FacetPills facets={facets} selected={{ topic, crop, region }} onToggle={toggleFacet} />

          {error && (
            <p style={{ color: '#d4a853' }}>Failed to load documents. Please try again.</p>
          )}

          {initialLoad && loading && !error && (
            <p style={{ color: '#8a9489' }}>Loading documents…</p>
          )}

          {!initialLoad && !error && (
            <>
              {loading && (
                <p style={{ color: '#8a9489', fontSize: 12, marginBottom: 10 }}>Updating…</p>
              )}

              {showEmptyState ? (
                hasActiveFilters ? (
                  <div
                    style={{
                      padding: '24px 18px',
                      borderRadius: 10,
                      border: '1px solid #2a3329',
                      background: '#141a15',
                      textAlign: 'center',
                    }}
                  >
                    <p style={{ color: '#d4cfc6', margin: '0 0 12px' }}>
                      No documents match your current filters.
                    </p>
                    <button
                      type="button"
                      onClick={clearFilters}
                      style={{
                        padding: '8px 16px',
                        borderRadius: 6,
                        border: '1px solid #3d6b4f',
                        background: '#1e3a28',
                        color: '#8ecfaa',
                        fontSize: 13,
                        fontFamily: 'Outfit, system-ui, sans-serif',
                        cursor: 'pointer',
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                ) : (
                  <p style={{ color: '#8a9489' }}>No documents published yet.</p>
                )
              ) : (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                    opacity: loading ? 0.6 : 1,
                    transition: 'opacity 0.15s',
                  }}
                >
                  {documents.map((doc) => (
                    <DocumentCard key={doc.id} doc={doc} />
                  ))}
                </div>
              )}

              {!showEmptyState && (
                <Pagination offset={offset} limit={LIMIT} total={total} onChange={handlePageChange} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
