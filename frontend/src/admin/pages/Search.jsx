import { useState } from 'react'
import { Search as SearchIcon, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { Input } from '../../components/ui/input'
import { Button } from '../../components/ui/button'
import { Card, CardContent } from '../../components/ui/card'
import { adminApi } from '../api'

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(10)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)

  async function handleSearch(e) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResults(null)
    setExpanded(null)
    try {
      const data = await adminApi.search(query.trim(), topK)
      setResults(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 font-admin max-w-[900px]">
      <div className="mb-5">
        <h1 className="text-lg font-semibold text-admin-text">Search Knowledge Base</h1>
        <p className="text-xs text-admin-muted mt-0.5">Semantic search over all indexed document chunks</p>
      </div>

      <form onSubmit={handleSearch} className="mb-5 space-y-3">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <SearchIcon size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-admin-muted pointer-events-none" />
            <Input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="e.g. maize storage best practices"
              className="pl-9"
            />
          </div>
          <Button type="submit" disabled={loading || !query.trim()}>
            {loading ? 'Searching…' : 'Search'}
          </Button>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-[11px] text-admin-muted whitespace-nowrap">
            Results: <span className="text-admin-text font-mono">{topK}</span>
          </label>
          <input
            type="range"
            min={3} max={20} step={1}
            value={topK}
            onChange={e => setTopK(Number(e.target.value))}
            className="w-32 accent-admin-accent"
          />
        </div>
      </form>

      {error && (
        <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2 mb-4">
          {error}
        </p>
      )}

      {results !== null && (
        <div>
          <p className="text-[11px] text-admin-muted mb-3">
            Found <span className="text-admin-text font-semibold">{results.length}</span> chunks
          </p>
          <div className="space-y-2">
            {results.length === 0 && (
              <p className="text-[12px] text-admin-muted py-6 text-center">
                No results found. Make sure documents have been processed and embedded.
              </p>
            )}
            {results.map((r, i) => {
              const payload = r.payload || {}
              const score = r.score || 0
              const url = payload.source_url || 'Unknown'
              const isOpen = expanded === i
              return (
                <Card key={i}>
                  <div
                    className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-admin-hover rounded-lg transition-colors"
                    onClick={() => setExpanded(isOpen ? null : i)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span
                        className="font-mono text-[11px] flex-shrink-0"
                        style={{ color: score > 0.7 ? '#22c55e' : score > 0.5 ? '#f59e0b' : '#71717a' }}
                      >
                        {score.toFixed(3)}
                      </span>
                      <span className="text-[12px] text-admin-text truncate">{url}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-admin-muted hover:text-admin-accent"
                        onClick={e => e.stopPropagation()}
                      >
                        <ExternalLink size={11} />
                      </a>
                      {isOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                    </div>
                  </div>
                  {isOpen && (
                    <CardContent className="pt-0 border-t border-admin-border">
                      <p className="text-[12px] text-zinc-300 leading-relaxed mb-3 whitespace-pre-wrap">
                        {payload.text || '(no text)'}
                      </p>
                      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-admin-muted">
                        {payload.topics?.length > 0 && <span>Topics: {payload.topics.join(', ')}</span>}
                        {payload.crops?.length > 0 && <span>Crops: {payload.crops.join(', ')}</span>}
                        {payload.document_type && <span>Type: {payload.document_type}</span>}
                        {payload.relevance_score != null && <span>Relevance: {payload.relevance_score}</span>}
                      </div>
                    </CardContent>
                  )}
                </Card>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
