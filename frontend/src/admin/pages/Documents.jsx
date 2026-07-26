import { Fragment, useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp, Clock3, ExternalLink, Pencil, Trash2 } from 'lucide-react'
import { adminApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Select } from '../../components/ui/select'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Alert } from '../../components/ui/alert'

const SITES = ['naro', 'agriculture', 'extension', 'ubos']
const STATUSES = ['discovered', 'queued', 'processing', 'processed', 'failed', 'skipped']
const PAGE_SIZE = 50

function isHttpUrl(value) {
  return /^https?:\/\//i.test((value || '').trim())
}

function formatDateTime(iso) {
  return iso ? iso.slice(0, 16).replace('T', ' ') : null
}

function processingIcon(level, size = 12) {
  if (level === 'error' || level === 'warning') return <AlertCircle size={size} />
  if (level === 'success') return <CheckCircle2 size={size} />
  return <Clock3 size={size} />
}

function ProcessingLogTooltip({ log, documentId, documentTitle }) {
  if (!log) return null

  const tooltipId = `processing-log-${documentId}`
  const iconTone = {
    error: 'text-red-400 hover:bg-red-500/10 focus-visible:ring-red-400',
    warning: 'text-yellow-400 hover:bg-yellow-500/10 focus-visible:ring-yellow-400',
    success: 'text-green-400 hover:bg-green-500/10 focus-visible:ring-green-400',
    info: 'text-blue-400 hover:bg-blue-500/10 focus-visible:ring-blue-400',
    default: 'text-admin-muted hover:bg-admin-hover focus-visible:ring-admin-accent',
  }[log.level] || 'text-admin-muted'

  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={`Processing information for ${documentTitle}`}
        aria-describedby={tooltipId}
        className={`inline-flex h-5 w-5 items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-1 ${iconTone}`}
        onClick={event => event.stopPropagation()}
      >
        {processingIcon(log.level, 13)}
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 hidden w-80 -translate-x-1/2 rounded-md border border-admin-border bg-zinc-950 px-3 py-2.5 text-left shadow-xl group-hover:block group-focus-within:block"
      >
        <span className="block text-[10px] font-semibold uppercase tracking-wider text-admin-muted">
          Processing outcome
        </span>
        <span className="mt-1 block text-[11px] leading-4 text-admin-text">
          {log.summary}
        </span>
        {log.details && (
          <span className="mt-2 block border-t border-admin-border pt-2">
            <span className="block text-[9px] font-semibold uppercase tracking-wider text-admin-muted">
              Stored detail
            </span>
            <span className="mt-1 block max-h-36 overflow-hidden whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-zinc-300">
              {log.details}
            </span>
          </span>
        )}
      </span>
    </span>
  )
}

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [site, setSite] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('discovered')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(null)
  const [relevanceThreshold, setRelevanceThreshold] = useState(null)
  const [publishingId, setPublishingId] = useState(null)
  const [publishErrors, setPublishErrors] = useState({})
  const [sourceUrlInputs, setSourceUrlInputs] = useState({})
  const [confirming, setConfirming] = useState(null) // { id, action: 'publish' | 'unpublish' | 'delete' } | null
  const [editingTitleId, setEditingTitleId] = useState(null)
  const [titleDrafts, setTitleDrafts] = useState({})
  const [savingTitleId, setSavingTitleId] = useState(null)
  const [titleErrors, setTitleErrors] = useState({})
  const [deletingId, setDeletingId] = useState(null)
  const [deleteErrors, setDeleteErrors] = useState({})

  useEffect(() => {
    load(0)
  }, [site, status, sort])

  useEffect(() => {
    adminApi.getConfig()
      .then((cfg) => setRelevanceThreshold(cfg?.crawl?.relevance_threshold ?? null))
      .catch(() => {}) // non-critical — the below-threshold hint just won't show
  }, [])

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

  function applyPublicationUpdate(id, updated) {
    setDocs(prev => prev.map(d => (
      d.id === id
        ? {
            ...d,
            publicly_visible: updated.publicly_visible,
            published_at: updated.published_at,
            published_by: updated.published_by,
            public_source_url: updated.public_source_url,
          }
        : d
    )))
  }

  function startEditTitle(doc) {
    setTitleDrafts(prev => ({ ...prev, [doc.id]: doc.title }))
    setTitleErrors(prev => ({ ...prev, [doc.id]: null }))
    setEditingTitleId(doc.id)
  }

  function cancelEditTitle() {
    setEditingTitleId(null)
  }

  async function saveTitle(doc) {
    const newTitle = (titleDrafts[doc.id] ?? '').trim()
    if (!newTitle) {
      setTitleErrors(prev => ({ ...prev, [doc.id]: 'Title cannot be empty.' }))
      return
    }
    if (newTitle === doc.title) {
      setEditingTitleId(null)
      return
    }
    setSavingTitleId(doc.id)
    setTitleErrors(prev => ({ ...prev, [doc.id]: null }))
    try {
      const updated = await adminApi.updateDocumentTitle(doc.id, newTitle)
      setDocs(prev => prev.map(d => (d.id === doc.id ? { ...d, title: updated.title } : d)))
      setEditingTitleId(null)
    } catch (e) {
      setTitleErrors(prev => ({ ...prev, [doc.id]: e.message }))
    } finally {
      setSavingTitleId(null)
    }
  }

  function requestPublish(doc) {
    const needsUrl = doc.url.startsWith('upload://') && !doc.public_source_url
    const enteredUrl = (sourceUrlInputs[doc.id] || '').trim()
    if (needsUrl && !isHttpUrl(enteredUrl)) {
      setPublishErrors(prev => ({ ...prev, [doc.id]: 'Enter a valid http:// or https:// URL first.' }))
      return
    }
    setPublishErrors(prev => ({ ...prev, [doc.id]: null }))
    setConfirming({ id: doc.id, action: 'publish' })
  }

  function requestUnpublish(doc) {
    setPublishErrors(prev => ({ ...prev, [doc.id]: null }))
    setConfirming({ id: doc.id, action: 'unpublish' })
  }

  function requestDelete(doc) {
    setDeleteErrors(prev => ({ ...prev, [doc.id]: null }))
    setConfirming({ id: doc.id, action: 'delete' })
  }

  function cancelConfirm() {
    setConfirming(null)
  }

  async function confirmAction(doc) {
    const action = confirming?.action
    setConfirming(null)
    if (action === 'delete') {
      setDeletingId(doc.id)
      setDeleteErrors(prev => ({ ...prev, [doc.id]: null }))
      try {
        await adminApi.deleteDocument(doc.id)
        const nextOffset = docs.length === 1 && offset > 0
          ? Math.max(0, offset - PAGE_SIZE)
          : offset
        await load(nextOffset)
      } catch (e) {
        setDeleteErrors(prev => ({ ...prev, [doc.id]: e.message }))
      } finally {
        setDeletingId(null)
      }
      return
    }

    setPublishingId(doc.id)
    setPublishErrors(prev => ({ ...prev, [doc.id]: null }))
    try {
      let body
      if (action === 'publish') {
        const needsUrl = doc.url.startsWith('upload://') && !doc.public_source_url
        body = { publicly_visible: true }
        if (needsUrl) body.public_source_url = (sourceUrlInputs[doc.id] || '').trim()
      } else {
        body = { publicly_visible: false }
      }
      const updated = await adminApi.updateDocumentPublication(doc.id, body)
      applyPublicationUpdate(doc.id, updated)
    } catch (e) {
      setPublishErrors(prev => ({ ...prev, [doc.id]: e.message }))
    } finally {
      setPublishingId(null)
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
                  <Fragment key={doc.id}>
                    <tr
                      key={doc.id}
                      onClick={() => {
                        setExpanded(expanded === doc.id ? null : doc.id)
                        setConfirming(null)
                        setEditingTitleId(null)
                      }}
                      className="border-b border-admin-border hover:bg-admin-hover cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 text-admin-text max-w-[240px] font-medium">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate">{doc.title}</span>
                          <button
                            type="button"
                            className="text-admin-muted hover:text-admin-text flex-shrink-0"
                            title="Edit title"
                            onClick={e => {
                              e.stopPropagation()
                              setExpanded(doc.id)
                              startEditTitle(doc)
                            }}
                          >
                            <Pencil size={11} />
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-admin-muted">{doc.site_name}</td>
                      <td className="px-4 py-3 text-admin-muted">{doc.document_type}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <Badge status={doc.status}>{doc.status}</Badge>
                          <ProcessingLogTooltip
                            log={doc.processing_log}
                            documentId={doc.id}
                            documentTitle={doc.title}
                          />
                        </div>
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
                        <td colSpan={7} className="px-4 py-4">
                          <div className="flex flex-col gap-3 text-[11px]" onClick={e => e.stopPropagation()}>
                            {editingTitleId === doc.id ? (
                              <div className="max-w-lg">
                                <label className="block text-zinc-600 mb-1">Title:</label>
                                <div className="flex items-center gap-2">
                                  <Input
                                    autoFocus
                                    value={titleDrafts[doc.id] ?? ''}
                                    onChange={e => setTitleDrafts(prev => ({ ...prev, [doc.id]: e.target.value }))}
                                    onKeyDown={e => {
                                      if (e.key === 'Enter') saveTitle(doc)
                                      if (e.key === 'Escape') cancelEditTitle()
                                    }}
                                    disabled={savingTitleId === doc.id}
                                  />
                                  <Button
                                    size="sm"
                                    onClick={() => saveTitle(doc)}
                                    disabled={savingTitleId === doc.id}
                                  >
                                    {savingTitleId === doc.id ? 'Saving…' : 'Save'}
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={cancelEditTitle}
                                    disabled={savingTitleId === doc.id}
                                  >
                                    Cancel
                                  </Button>
                                </div>
                                {titleErrors[doc.id] && (
                                  <div className="text-red-400 mt-1">{titleErrors[doc.id]}</div>
                                )}
                              </div>
                            ) : (
                              <div className="flex items-center gap-2">
                                <span className="text-zinc-600">Title:</span>
                                <span className="text-admin-text">{doc.title}</span>
                                <button
                                  type="button"
                                  className="text-admin-muted hover:text-admin-text"
                                  title="Edit title"
                                  onClick={() => startEditTitle(doc)}
                                >
                                  <Pencil size={11} />
                                </button>
                              </div>
                            )}

                            <div className="flex items-center gap-2 text-admin-muted">
                              <span className="text-zinc-600">URL:</span>
                              <a
                                href={doc.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-admin-accent hover:underline flex items-center gap-1 truncate"
                              >
                                {doc.url}
                                <ExternalLink size={10} />
                              </a>
                            </div>

                            <div className="flex items-center gap-2">
                              <span className="text-zinc-600">Publication:</span>
                              {doc.publicly_visible ? (
                                <Badge variant="success">
                                  Published
                                  {doc.published_at ? ` · ${formatDateTime(doc.published_at)}` : ''}
                                  {doc.published_by ? ` by ${doc.published_by}` : ''}
                                </Badge>
                              ) : (
                                <Badge variant="default">Not published</Badge>
                              )}
                            </div>

                            {doc.classification_relevance_score != null &&
                              relevanceThreshold != null &&
                              doc.classification_relevance_score < relevanceThreshold && (
                                <Alert variant="warning" className="py-2 px-3 text-[11px]">
                                  This document's relevance score ({doc.classification_relevance_score.toFixed(1)})
                                  is below the public threshold ({relevanceThreshold}) — publishing it will not
                                  make it appear in the public library until it's reclassified above that
                                  threshold.
                                </Alert>
                              )}

                            {doc.summary && (
                              <div>
                                <div className="text-zinc-600 mb-1">
                                  Summary — this is what becomes publicly visible, not the document itself:
                                </div>
                                <p className="text-admin-text leading-relaxed">{doc.summary}</p>
                              </div>
                            )}

                            {doc.key_practices?.length > 0 && (
                              <div>
                                <div className="text-zinc-600 mb-1">Key practices:</div>
                                <ul className="list-disc pl-4 text-admin-text space-y-0.5">
                                  {doc.key_practices.map((practice, i) => (
                                    <li key={i}>{practice}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {(doc.topics?.length > 0 || doc.crops?.length > 0 || doc.regions?.length > 0) && (
                              <div className="flex flex-wrap gap-1">
                                {[...doc.topics, ...doc.crops, ...doc.regions].map((tag, i) => (
                                  <Badge key={`${tag}-${i}`} variant="default">{tag}</Badge>
                                ))}
                              </div>
                            )}

                            {doc.url.startsWith('upload://') && !doc.public_source_url && (
                              <div className="max-w-md">
                                <label className="block text-zinc-600 mb-1">
                                  Public source URL — required before this uploaded document can be published:
                                </label>
                                <Input
                                  type="url"
                                  placeholder="https://…"
                                  value={sourceUrlInputs[doc.id] || ''}
                                  onChange={e => setSourceUrlInputs(prev => ({ ...prev, [doc.id]: e.target.value }))}
                                />
                              </div>
                            )}

                            {confirming?.id === doc.id ? (
                              <Alert
                                variant={confirming.action === 'publish' ? 'info' : 'warning'}
                                className="py-2.5 px-3 text-[11px]"
                              >
                                <div className="mb-2">
                                  {confirming.action === 'publish' ? (
                                    <>
                                      Publish this document? Its summary, key practices, and up to 3 short
                                      excerpts (never the full document) will become publicly visible
                                      immediately.
                                    </>
                                  ) : confirming.action === 'unpublish' ? (
                                    <>Unpublish this document? It will immediately stop appearing in the public library.</>
                                  ) : (
                                    <>
                                      Permanently delete this document? Its source file, indexed chunks, and
                                      search vectors will be removed from the knowledge base. This cannot be undone.
                                    </>
                                  )}
                                </div>
                                <div className="flex items-center gap-2">
                                  <Button
                                    size="sm"
                                    variant={confirming.action === 'publish' ? 'default' : 'destructive'}
                                    onClick={() => confirmAction(doc)}
                                  >
                                    {confirming.action === 'publish'
                                      ? 'Yes, publish'
                                      : confirming.action === 'unpublish'
                                        ? 'Yes, unpublish'
                                        : 'Yes, delete permanently'}
                                  </Button>
                                  <Button variant="outline" size="sm" onClick={cancelConfirm}>
                                    Cancel
                                  </Button>
                                </div>
                              </Alert>
                            ) : (
                              <div className="flex items-center gap-3 pt-1">
                                {doc.publicly_visible ? (
                                  <Button
                                    variant="destructive"
                                    size="sm"
                                    disabled={publishingId === doc.id}
                                    onClick={() => requestUnpublish(doc)}
                                  >
                                    {publishingId === doc.id ? 'Unpublishing…' : 'Unpublish'}
                                  </Button>
                                ) : (
                                  <Button
                                    size="sm"
                                    disabled={doc.status !== 'processed' || publishingId === doc.id}
                                    onClick={() => requestPublish(doc)}
                                  >
                                    {publishingId === doc.id ? 'Publishing…' : 'Publish'}
                                  </Button>
                                )}
                                {!doc.publicly_visible && doc.status !== 'processed' && (
                                  <span className="text-admin-muted">
                                    Only processed documents can be published.
                                  </span>
                                )}
                                <Button
                                  variant="destructive"
                                  size="sm"
                                  disabled={deletingId === doc.id || ['queued', 'processing', 'discovered'].includes(doc.status)}
                                  onClick={() => requestDelete(doc)}
                                >
                                  <Trash2 size={12} />
                                  {deletingId === doc.id ? 'Deleting…' : 'Delete'}
                                </Button>
                                {publishErrors[doc.id] && (
                                  <span className="text-red-400">{publishErrors[doc.id]}</span>
                                )}
                                {deleteErrors[doc.id] && (
                                  <span className="text-red-400">{deleteErrors[doc.id]}</span>
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
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
