import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { adminApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Select } from '../../components/ui/select'
import { Button } from '../../components/ui/button'

const SITES = ['naro', 'agriculture', 'extension', 'ubos']
const STATUSES = ['discovered', 'queued', 'processing', 'processed', 'failed', 'skipped']
const PAGE_SIZE = 50

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [site, setSite] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('discovered')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    load(0)
  }, [site, status, sort])

  async function load(newOffset) {
    setLoading(true)
    try {
      const data = await adminApi.getDocuments({
        site: site || undefined,
        status: status || undefined,
        sort,
        offset: newOffset,
        limit: PAGE_SIZE,
      })
      setDocs(data.items)
      setTotal(data.total)
      setOffset(newOffset)
      setExpanded(null)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="p-6 font-admin max-w-[1200px]">
      <div className="mb-5">
        <h1 className="text-lg font-semibold text-admin-text">Documents</h1>
        <p className="text-xs text-admin-muted mt-0.5">{total.toLocaleString()} total</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="w-36">
          <Select value={site} onChange={e => setSite(e.target.value)}>
            <option value="">All sites</option>
            {SITES.map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
        </div>
        <div className="w-40">
          <Select value={status} onChange={e => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
        </div>
        <div className="w-44">
          <Select value={sort} onChange={e => setSort(e.target.value)}>
            <option value="discovered">Sort: Newest first</option>
            <option value="relevance">Sort: Relevance</option>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={() => load(0)} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </Button>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-admin-border">
                  {['Title', 'Site', 'Type', 'Status', 'Relevance', 'Discovered'].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-[10px] font-semibold text-admin-muted uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                  <th className="px-4 py-3 w-8" />
                </tr>
              </thead>
              <tbody>
                {docs.map(doc => (
                  <>
                    <tr
                      key={doc.id}
                      onClick={() => setExpanded(expanded === doc.id ? null : doc.id)}
                      className="border-b border-admin-border hover:bg-admin-hover cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 text-admin-text max-w-[240px] truncate font-medium">
                        {doc.title}
                      </td>
                      <td className="px-4 py-3 text-admin-muted">{doc.site_name}</td>
                      <td className="px-4 py-3 text-admin-muted">{doc.document_type}</td>
                      <td className="px-4 py-3">
                        <Badge status={doc.status}>{doc.status}</Badge>
                      </td>
                      <td className="px-4 py-3 font-mono text-admin-muted">
                        {doc.relevance_score != null ? doc.relevance_score.toFixed(1) : '—'}
                      </td>
                      <td className="px-4 py-3 text-admin-muted">
                        {doc.discovered_at ? doc.discovered_at.slice(0, 16).replace('T', ' ') : '—'}
                      </td>
                      <td className="px-4 py-3 text-admin-muted">
                        {expanded === doc.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                      </td>
                    </tr>
                    {expanded === doc.id && (
                      <tr key={`${doc.id}-exp`} className="bg-admin-hover border-b border-admin-border">
                        <td colSpan={7} className="px-4 py-3">
                          <div className="flex items-center gap-2 text-[11px] text-admin-muted">
                            <span className="text-zinc-600">URL:</span>
                            <a
                              href={doc.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-admin-accent hover:underline flex items-center gap-1 truncate"
                              onClick={e => e.stopPropagation()}
                            >
                              {doc.url}
                              <ExternalLink size={10} />
                            </a>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {!loading && docs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-admin-muted text-[12px]">
                      No documents found. Run a crawl to populate the database.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-[12px] text-admin-muted">
          <span>Page {currentPage} of {totalPages}</span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0 || loading}
              onClick={() => load(offset - PAGE_SIZE)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => load(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
