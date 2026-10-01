import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Link as RouterLink } from 'react-router-dom'
import { Upload, Link2, FileText, Loader2, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import { adminApi } from '../api'
import { Input } from '../../components/ui/input'
import { Button } from '../../components/ui/button'

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/msword': ['.doc'],
  'text/html': ['.html', '.htm'],
}

const MAX_FILES = 20
const MAX_FILE_SIZE = 50 * 1024 * 1024

function ResultBanner({ result, onDismiss, label }) {
  if (!result) return null

  // Ingestion now runs in the Prefect worker rather than in the API process,
  // so a successful submission returns immediately with a flow_run_id and the
  // outcome (processed / skipped / relevance score) is only known later.
  if (result.status === 'queued') {
    return (
      <div className="flex items-start gap-2.5 rounded-md border border-blue-500/20 bg-blue-500/5 px-4 py-3 text-[12px] text-blue-300">
        <CheckCircle size={14} className="mt-0.5 flex-shrink-0" />
        <div>
          {label && <span className="font-medium">{label}: </span>}
          Queued for processing.{' '}
          {result.document_id ? (
            <RouterLink
              to={`/admin/documents?highlight=${result.document_id}`}
              className="underline hover:text-blue-200"
            >
              Track its progress in Documents
            </RouterLink>
          ) : (
            'It will appear in Documents once indexing finishes.'
          )}
        </div>
        {onDismiss && <button type="button" onClick={onDismiss} className="ml-auto text-blue-500 hover:text-blue-300">×</button>}
      </div>
    )
  }

  if (result.status === 'processed') {
    const score = typeof result.relevance_score === 'number'
      ? result.relevance_score.toFixed(1) : 'N/A'
    return (
      <div className="flex items-start gap-2.5 bg-green-500/5 border border-green-500/20 rounded-md px-4 py-3 text-[12px] text-green-300">
        <CheckCircle size={14} className="flex-shrink-0 mt-0.5" />
        <div>
          {label && <span className="font-medium">{label}: </span>}
          Document added successfully — {result.chunks} chunks indexed. Relevance: {score}/10
        </div>
        {onDismiss && <button type="button" onClick={onDismiss} className="ml-auto text-green-500 hover:text-green-300">×</button>}
      </div>
    )
  }

  if (result.status === 'skipped') {
    const score = typeof result.relevance_score === 'number'
      ? ` (score: ${result.relevance_score.toFixed(1)}/10)` : ''
    return (
      <div className="flex items-start gap-2.5 bg-yellow-500/5 border border-yellow-500/20 rounded-md px-4 py-3 text-[12px] text-yellow-300">
        <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
        <div>
          {label && <span className="font-medium">{label}: </span>}
          {result.reason === 'low_relevance'
            ? `Document rejected — not relevant enough to pre-harvest or post-harvest crop knowledge${score}.`
            : 'Document skipped — no extractable text content was found.'}
        </div>
        {onDismiss && <button type="button" onClick={onDismiss} className="ml-auto text-yellow-500 hover:text-yellow-300">×</button>}
      </div>
    )
  }

  if (result.status === 'duplicate') {
    return (
      <div className="flex items-start gap-2.5 rounded-md border border-blue-500/20 bg-blue-500/5 px-4 py-3 text-[12px] text-blue-300">
        <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
        <div>
          {label && <span className="font-medium">{label}: </span>}
          Already in the knowledge base
          {result.existing_title ? ` as “${result.existing_title}”` : ''}. Nothing was uploaded or indexed again.
        </div>
        {onDismiss && <button type="button" onClick={onDismiss} className="ml-auto text-blue-500 hover:text-blue-300">×</button>}
      </div>
    )
  }

  return (
    <div className="flex items-start gap-2.5 bg-red-500/5 border border-red-500/20 rounded-md px-4 py-3 text-[12px] text-red-300">
      <XCircle size={14} className="flex-shrink-0 mt-0.5" />
      <div>
        {label && <span className="font-medium">{label}: </span>}
        {result.error || 'Ingestion failed. Check the application logs.'}
      </div>
      {onDismiss && <button type="button" onClick={onDismiss} className="ml-auto text-red-500 hover:text-red-300">×</button>}
    </div>
  )
}

function FileTab() {
  const [items, setItems] = useState([])
  const [site, setSite] = useState('manual')
  const [loading, setLoading] = useState(false)
  const [selectionError, setSelectionError] = useState(null)

  const onDrop = useCallback((accepted, rejected) => {
    setItems(current => {
      const known = new Set(current.map(item => (
        `${item.file.name}:${item.file.size}:${item.file.lastModified}`
      )))
      const additions = accepted
        .filter(file => !known.has(`${file.name}:${file.size}:${file.lastModified}`))
        .slice(0, Math.max(0, MAX_FILES - current.length))
        .map(file => ({
          id: `${file.name}:${file.size}:${file.lastModified}`,
          file,
          title: '',
          state: 'queued',
          result: null,
        }))
      return [...current, ...additions]
    })

    const errors = rejected.flatMap(({ file, errors: fileErrors }) => (
      fileErrors.map(error => {
        if (error.code === 'file-too-large') return `${file.name} exceeds the 50 MB limit.`
        if (error.code === 'file-invalid-type') return `${file.name} is not a supported document type.`
        if (error.code === 'too-many-files') return `Select no more than ${MAX_FILES} files at once.`
        return `${file.name}: ${error.message}`
      })
    ))
    setSelectionError(errors.length ? errors.join(' ') : null)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxFiles: MAX_FILES,
    maxSize: MAX_FILE_SIZE,
    multiple: true,
    disabled: loading,
  })

  function updateItem(id, changes) {
    setItems(current => current.map(item => (
      item.id === id ? { ...item, ...changes } : item
    )))
  }

  function removeItem(id) {
    setItems(current => current.filter(item => item.id !== id))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const queued = items.filter(item => item.state === 'queued')
    if (!queued.length) return

    setLoading(true)
    setSelectionError(null)

    for (const item of queued) {
      updateItem(item.id, { state: 'processing', result: null })
      try {
        const result = await adminApi.ingestFile(item.file, item.title, site)
        updateItem(item.id, { state: 'finished', result })
      } catch (error) {
        updateItem(item.id, {
          state: 'finished',
          result: { status: 'failed', error: error.message },
        })
      }
    }

    setLoading(false)
  }

  const queuedCount = items.filter(item => item.state === 'queued').length

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={[
          'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
          isDragActive
            ? 'border-admin-accent bg-admin-accent/5'
            : 'border-admin-border hover:border-zinc-600 hover:bg-admin-hover',
        ].join(' ')}
      >
        <input {...getInputProps()} />
        <Upload size={20} className="text-admin-muted mx-auto mb-2" />
        <p className="text-[12px] text-admin-text font-medium mb-1">
          {isDragActive ? 'Drop documents here' : 'Drop documents or click to browse'}
        </p>
        <p className="text-[11px] text-admin-muted">
          Up to {MAX_FILES} PDF, DOCX, DOC, or HTML files · max 50 MB each
        </p>
      </div>

      {selectionError && (
        <div className="flex items-start gap-2 rounded-md border border-red-500/20 bg-red-500/5 px-4 py-3 text-[12px] text-red-300">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <span>{selectionError}</span>
        </div>
      )}

      {items.length > 0 && (
        <div className="overflow-hidden rounded-md border border-admin-border bg-admin-surface">
          <div className="flex items-center justify-between border-b border-admin-border px-4 py-2.5">
            <span className="text-[11px] font-medium text-admin-text">
              {items.length} document{items.length === 1 ? '' : 's'} selected
            </span>
            {!loading && (
              <button
                type="button"
                onClick={() => setItems([])}
                className="text-[10px] text-admin-muted hover:text-admin-text"
              >
                Clear all
              </button>
            )}
          </div>

          <div className="divide-y divide-admin-border">
            {items.map(item => (
              <div key={item.id} className="space-y-2.5 px-4 py-3">
                <div className="flex items-start gap-2.5">
                  {item.state === 'processing'
                    ? <Loader2 size={15} className="mt-0.5 flex-shrink-0 animate-spin text-admin-accent" />
                    : <FileText size={15} className="mt-0.5 flex-shrink-0 text-admin-accent" />}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-medium text-admin-text">{item.file.name}</p>
                    <p className="text-[10px] text-admin-muted">
                      {(item.file.size / 1024).toFixed(1)} KB
                      {item.state === 'processing' && ' · Processing…'}
                    </p>
                  </div>
                  {item.state === 'queued' && !loading && (
                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      aria-label={`Remove ${item.file.name}`}
                      className="text-admin-muted hover:text-red-400"
                    >
                      ×
                    </button>
                  )}
                </div>

                {item.state === 'queued' && (
                  <Input
                    value={item.title}
                    onChange={event => updateItem(item.id, { title: event.target.value })}
                    placeholder="Optional document title"
                  />
                )}

                {item.result && <ResultBanner result={item.result} label={item.file.name} />}
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <label className="block text-[10px] font-medium text-admin-muted uppercase tracking-wider mb-1.5">
          Source / site name
        </label>
        <Input
          value={site}
          onChange={e => setSite(e.target.value)}
          placeholder="manual"
          disabled={loading}
        />
      </div>

      <Button type="submit" disabled={!queuedCount || loading}>
        {loading && <Loader2 size={13} className="animate-spin" />}
        {loading
          ? 'Processing documents…'
          : queuedCount
            ? `Add ${queuedCount} Document${queuedCount === 1 ? '' : 's'} to Knowledge Base`
            : 'Add Documents to Knowledge Base'}
      </Button>
    </form>
  )
}

function UrlTab() {
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [site, setSite] = useState('manual')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const r = await adminApi.ingestUrl(url.trim(), title, site)
      setResult(r)
      if (r.status === 'processed') { setUrl(''); setTitle('') }
    } catch (e) {
      setResult({ status: 'failed', error: e.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-[10px] font-medium text-admin-muted uppercase tracking-wider mb-1.5">
          Document URL
        </label>
        <div className="relative">
          <Link2 size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-admin-muted pointer-events-none" />
          <Input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://example.org/maize-guide.pdf"
            className="pl-9"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[10px] font-medium text-admin-muted uppercase tracking-wider mb-1.5">
            Title (optional)
          </label>
          <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Document title" />
        </div>
        <div>
          <label className="block text-[10px] font-medium text-admin-muted uppercase tracking-wider mb-1.5">
            Source / site name
          </label>
          <Input value={site} onChange={e => setSite(e.target.value)} placeholder="manual" />
        </div>
      </div>

      <ResultBanner result={result} onDismiss={() => setResult(null)} />

      <Button type="submit" disabled={!url.trim() || loading}>
        {loading && <Loader2 size={13} className="animate-spin" />}
        {loading ? 'Processing…' : 'Add URL to Knowledge Base'}
      </Button>
    </form>
  )
}

export default function AddDocumentPage() {
  const [tab, setTab] = useState('file')

  return (
    <div className="p-6 font-admin max-w-[700px]">
      <div className="mb-5">
        <h1 className="text-lg font-semibold text-admin-text">Add Document(s)</h1>
        <p className="text-xs text-admin-muted mt-0.5">
          Upload a file or provide a URL to add a document to the knowledge base.
          Documents below the relevance threshold are rejected automatically.
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 p-1 bg-admin-surface border border-admin-border rounded-md w-fit mb-5">
        {[
          { id: 'file', label: '📁 Upload File' },
          { id: 'url', label: '🔗 From URL' },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={[
              'px-4 py-1.5 rounded text-[12px] font-medium transition-colors',
              tab === t.id
                ? 'bg-admin-active text-admin-text'
                : 'text-admin-muted hover:text-admin-text',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'file' ? <FileTab /> : <UrlTab />}
    </div>
  )
}
