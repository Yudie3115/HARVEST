import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
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

function ResultBanner({ result, onDismiss }) {
  if (!result) return null

  if (result.status === 'processed') {
    const score = typeof result.relevance_score === 'number'
      ? result.relevance_score.toFixed(1) : 'N/A'
    return (
      <div className="flex items-start gap-2.5 bg-green-500/5 border border-green-500/20 rounded-md px-4 py-3 text-[12px] text-green-300">
        <CheckCircle size={14} className="flex-shrink-0 mt-0.5" />
        <div>
          Document added successfully — {result.chunks} chunks indexed. Relevance: {score}/10
        </div>
        <button onClick={onDismiss} className="ml-auto text-green-500 hover:text-green-300">×</button>
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
          {result.reason === 'low_relevance'
            ? `Document rejected — not relevant enough to post-harvest knowledge${score}.`
            : 'Document skipped — no extractable text content was found.'}
        </div>
        <button onClick={onDismiss} className="ml-auto text-yellow-500 hover:text-yellow-300">×</button>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-2.5 bg-red-500/5 border border-red-500/20 rounded-md px-4 py-3 text-[12px] text-red-300">
      <XCircle size={14} className="flex-shrink-0 mt-0.5" />
      <div>{result.error || 'Ingestion failed. Check the application logs.'}</div>
      <button onClick={onDismiss} className="ml-auto text-red-500 hover:text-red-300">×</button>
    </div>
  )
}

function FileTab() {
  const [file, setFile] = useState(null)
  const [title, setTitle] = useState('')
  const [site, setSite] = useState('manual')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const onDrop = useCallback(accepted => {
    if (accepted[0]) setFile(accepted[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: ACCEPTED, maxFiles: 1,
  })

  async function handleSubmit(e) {
    e.preventDefault()
    if (!file) return
    setLoading(true)
    setResult(null)
    try {
      const r = await adminApi.ingestFile(file, title, site)
      setResult(r)
      if (r.status === 'processed') { setFile(null); setTitle('') }
    } catch (e) {
      setResult({ status: 'failed', error: e.message })
    } finally {
      setLoading(false)
    }
  }

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
        {file ? (
          <div className="flex items-center justify-center gap-2.5 text-admin-text">
            <FileText size={18} className="text-admin-accent" />
            <div className="text-left">
              <p className="text-[13px] font-medium">{file.name}</p>
              <p className="text-[11px] text-admin-muted">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
          </div>
        ) : (
          <>
            <Upload size={20} className="text-admin-muted mx-auto mb-2" />
            <p className="text-[12px] text-admin-text font-medium mb-1">
              {isDragActive ? 'Drop file here' : 'Drop a file or click to browse'}
            </p>
            <p className="text-[11px] text-admin-muted">PDF, DOCX, DOC, HTML · max 50 MB</p>
          </>
        )}
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

      <Button type="submit" disabled={!file || loading}>
        {loading && <Loader2 size={13} className="animate-spin" />}
        {loading ? 'Processing…' : 'Add File to Knowledge Base'}
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
        <h1 className="text-lg font-semibold text-admin-text">Add Document</h1>
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
