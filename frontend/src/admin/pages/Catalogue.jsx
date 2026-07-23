import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Check, ChevronDown, ChevronUp, RefreshCw, X } from 'lucide-react'
import { adminApi } from '../api'

const score = (value) => value == null ? '—' : value.toFixed(3)

function Status({ value }) {
  const tones = {
    pending: 'border-amber-900/70 bg-amber-950/40 text-amber-400',
    publishing: 'border-blue-900/70 bg-blue-950/40 text-blue-400',
    approved: 'border-green-900/70 bg-green-950/40 text-green-400',
    publish_failed: 'border-red-900/70 bg-red-950/40 text-red-400',
    rejected: 'border-zinc-700 bg-zinc-800 text-zinc-400',
    retracted: 'border-zinc-700 bg-zinc-800 text-zinc-400',
  }
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase ${tones[value] || tones.rejected}`}>
      {value.replace('_', ' ')}
    </span>
  )
}

function Candidate({ item, action, busy }) {
  const [open, setOpen] = useState(false)
  const awaiting = ['pending', 'publish_failed'].includes(item.status)

  return (
    <article className="border-b border-admin-border">
      <button
        onClick={() => setOpen((value) => !value)}
        className="grid w-full grid-cols-[1fr_auto] gap-4 px-4 py-4 text-left hover:bg-admin-hover"
      >
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Status value={item.status} />
            <span className="font-mono text-[10px] text-admin-muted">Grounding {score(item.grounding_score)}</span>
            <span className="font-mono text-[10px] text-admin-muted">Curator {score(item.llm_score)}</span>
          </div>
          <h2 className="m-0 text-[13px] font-medium leading-5 text-admin-text">{item.question_en}</h2>
        </div>
        {open ? <ChevronUp size={14} className="mt-1 text-admin-muted" /> : <ChevronDown size={14} className="mt-1 text-admin-muted" />}
      </button>

      {open && (
        <div className="border-t border-admin-border bg-zinc-950/40 px-4 py-4">
          <p className="whitespace-pre-wrap text-[12px] leading-5 text-zinc-300">{item.answer_en}</p>
          {item.sources?.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-admin-muted">Sources</p>
              {item.sources.map((source, index) => (
                <p key={index} className="m-0 truncate text-[11px] text-zinc-500">
                  {source.title || source.site_name || source.url}
                </p>
              ))}
            </div>
          )}
          <div className="mt-4 grid grid-cols-2 gap-3 rounded border border-admin-border bg-black/20 p-3 text-[10px] text-admin-muted sm:grid-cols-4">
            <span>Attempts <b className="text-admin-text">{item.publish_attempts}</b></span>
            <span>Duplicates <b className="text-admin-text">{item.candidate_duplicate_count}</b></span>
            <span>Served <b className="text-admin-text">{item.served_count}</b></span>
            <span>Helpful <b className="text-admin-text">{item.helpful_count}</b></span>
          </div>
          {item.publish_error && (
            <p className="mt-3 flex items-start gap-2 rounded border border-red-950 bg-red-950/30 p-3 font-mono text-[10px] text-red-400">
              <AlertTriangle size={13} className="shrink-0" /> {item.publish_error}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {awaiting && (
              <button
                disabled={busy}
                onClick={() => action(item.status === 'publish_failed' ? 'retry' : 'approve', item.id)}
                className="inline-flex items-center gap-1.5 rounded bg-admin-accent px-3 py-1.5 text-[11px] font-medium text-black disabled:opacity-50"
              >
                {item.status === 'publish_failed' ? <RefreshCw size={12} /> : <Check size={12} />}
                {item.status === 'publish_failed' ? 'Retry publication' : 'Approve & publish'}
              </button>
            )}
            {awaiting && item.status !== 'publish_failed' && (
              <button
                disabled={busy}
                onClick={() => action('reject', item.id)}
                className="inline-flex items-center gap-1.5 rounded border border-admin-border px-3 py-1.5 text-[11px] text-zinc-400 hover:text-white disabled:opacity-50"
              >
                <X size={12} /> Reject
              </button>
            )}
            {item.status === 'approved' && (
              <button
                disabled={busy}
                onClick={() => action('retract', item.id)}
                className="inline-flex items-center gap-1.5 rounded border border-red-950 px-3 py-1.5 text-[11px] text-red-400 disabled:opacity-50"
              >
                Retract
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  )
}

export default function Catalogue() {
  const [tab, setTab] = useState('pending')
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = tab === 'pending'
        ? await adminApi.getCataloguePending()
        : await adminApi.getCatalogueApproved()
      setData(result)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => { load() }, [load])

  async function action(kind, id) {
    setBusy(id)
    try {
      if (kind === 'approve') await adminApi.approveCatalogue(id)
      if (kind === 'reject') await adminApi.rejectCatalogue(id)
      if (kind === 'retract') await adminApi.retractCatalogue(id)
      if (kind === 'retry') await adminApi.retryCatalogue(id)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="max-w-[1000px] p-6 font-admin">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="m-0 text-lg font-semibold text-admin-text">Q&A Catalogue</h1>
          <p className="mt-1 text-xs text-admin-muted">Review grounded chat answers before they become public.</p>
        </div>
        <button onClick={load} className="rounded border border-admin-border p-2 text-admin-muted hover:text-white" aria-label="Refresh">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="mb-3 flex gap-1 border-b border-admin-border">
        {[
          ['pending', 'Review queue'],
          ['approved', 'Published & archived'],
        ].map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`border-b-2 px-3 py-2 text-[11px] ${tab === value ? 'border-admin-accent text-white' : 'border-transparent text-admin-muted'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="rounded border border-red-950 bg-red-950/30 p-3 text-xs text-red-400">{error}</p>}
      <div className="overflow-hidden rounded border border-admin-border bg-admin-surface">
        {loading ? (
          <p className="py-12 text-center text-xs text-admin-muted">Loading catalogue…</p>
        ) : data.items.length === 0 ? (
          <p className="py-12 text-center text-xs text-admin-muted">
            {tab === 'pending' ? 'No candidates are waiting for review.' : 'No reviewed entries yet.'}
          </p>
        ) : data.items.map((item) => (
          <Candidate key={item.id} item={item} action={action} busy={busy === item.id} />
        ))}
      </div>
    </div>
  )
}
