import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { adminApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'

// ── helpers ──────────────────────────────────────────────────────────────────

function f1Color(f1) {
  if (f1 == null) return '#52525b'
  if (f1 >= 0.7)  return '#22c55e'
  if (f1 >= 0.5)  return '#f59e0b'
  return '#f43f5e'
}

function F1Badge({ value }) {
  if (value == null) return <span style={{ color: '#52525b' }} className="font-mono text-xs">—</span>
  return (
    <span
      className="font-mono text-xs font-semibold px-1.5 py-0.5 rounded"
      style={{ color: f1Color(value), background: f1Color(value) + '22' }}
    >
      {value.toFixed(3)}
    </span>
  )
}

function StatCard({ label, value, sub, accent }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-[10px] font-semibold text-admin-muted uppercase tracking-widest mb-2">{label}</p>
        <p
          className="font-mono text-3xl font-bold leading-none"
          style={{ color: accent || '#f4f4f5', fontFamily: '"IBM Plex Mono", monospace' }}
        >
          {value}
        </p>
        {sub && <p className="text-[11px] text-admin-muted mt-1.5">{sub}</p>}
      </CardContent>
    </Card>
  )
}

const BAR_COLORS = ['#f43f5e', '#f59e0b', '#22c55e', '#22c55e']

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-zinc-900 border border-admin-border rounded px-3 py-2 text-xs shadow-xl">
      <p className="text-admin-muted mb-0.5">F1 {label}</p>
      <p className="text-white font-mono font-semibold">{payload[0].value} messages</p>
    </div>
  )
}

function truncate(str, n) {
  if (!str) return '—'
  return str.length > n ? str.slice(0, n) + '…' : str
}

// ── row ──────────────────────────────────────────────────────────────────────

function MessageRow({ item }) {
  const [open, setOpen] = useState(false)
  const bs = item.bert_score || {}

  return (
    <>
      <tr
        className="border-b border-admin-border hover:bg-admin-hover cursor-pointer transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <td className="px-3 py-2.5 text-[12px] text-admin-muted max-w-[200px]">
          {truncate(item.question, 80)}
        </td>
        <td className="px-3 py-2.5 text-[12px] text-admin-text max-w-[220px]">
          {truncate(item.answer, 80)}
        </td>
        <td className="px-3 py-2.5 text-center">
          <F1Badge value={bs.f1} />
        </td>
        <td className="px-3 py-2.5 text-center font-mono text-[11px] text-admin-muted">
          {bs.precision != null ? bs.precision.toFixed(3) : '—'}
        </td>
        <td className="px-3 py-2.5 text-center font-mono text-[11px] text-admin-muted">
          {bs.recall != null ? bs.recall.toFixed(3) : '—'}
        </td>
        <td className="px-3 py-2.5 text-[11px] text-admin-muted whitespace-nowrap">
          {item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
        </td>
        <td className="px-3 py-2.5 text-admin-muted">
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </td>
      </tr>

      {open && (
        <tr className="border-b border-admin-border bg-zinc-900/40">
          <td colSpan={7} className="px-4 py-3 space-y-3">
            <div>
              <p className="text-[9px] font-semibold text-admin-muted uppercase tracking-widest mb-1">Question</p>
              <p className="text-[12px] text-admin-text leading-relaxed">{item.question || '—'}</p>
            </div>
            <div>
              <p className="text-[9px] font-semibold text-admin-muted uppercase tracking-widest mb-1">Answer</p>
              <p className="text-[12px] text-admin-text leading-relaxed whitespace-pre-wrap">{item.answer}</p>
            </div>
            <div className="flex gap-6 text-[11px] text-admin-muted">
              <span>Model: <span className="text-admin-text font-mono">{bs.model || '—'}</span></span>
              <span>Scored at: <span className="text-admin-text">{bs.scored_at ? new Date(bs.scored_at).toLocaleString() : '—'}</span></span>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── page ─────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20

export default function ChatQuality() {
  const [stats, setStats]   = useState(null)
  const [items, setItems]   = useState([])
  const [total, setTotal]   = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminApi.getChatQualityStats().then(setStats).catch(console.error)
  }, [])

  useEffect(() => {
    setLoading(true)
    adminApi.getChatQuality({ offset, limit: PAGE_SIZE })
      .then(data => { setItems(data.items); setTotal(data.total) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [offset])

  const meanF1 = stats?.mean_f1 != null ? stats.mean_f1.toFixed(3) : '—'
  const pages  = Math.ceil(total / PAGE_SIZE)
  const page   = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="p-6 max-w-[1200px] font-admin">

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-admin-text">Chat Quality</h1>
        <p className="text-xs text-admin-muted mt-0.5">
          Answer faithfulness scores — how well responses are grounded in retrieved sources
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <StatCard
          label="Mean F1 Score"
          value={meanF1}
          accent={stats?.mean_f1 != null ? f1Color(stats.mean_f1) : undefined}
          sub="across all scored messages"
        />
        <StatCard
          label="Scored Messages"
          value={stats ? stats.total_scored.toLocaleString() : '—'}
          sub="have a faithfulness score"
        />
        <StatCard
          label="Unscored"
          value={stats ? stats.total_unscored.toLocaleString() : '—'}
          sub="pre-feature or scoring failed"
          accent="#52525b"
        />
      </div>

      {/* Distribution chart */}
      {stats?.distribution && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle>F1 Distribution</CardTitle>
            <p className="text-[11px] text-admin-muted">Messages by faithfulness score bucket</p>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={stats.distribution} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" />
                <XAxis
                  dataKey="range"
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {stats.distribution.map((_, i) => (
                    <Cell key={i} fill={BAR_COLORS[i]} fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Messages table */}
      <Card>
        <CardHeader>
          <CardTitle>Scored Messages</CardTitle>
          <p className="text-[11px] text-admin-muted">Click a row to expand the full question and answer</p>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <p className="text-[12px] text-admin-muted text-center py-10">Loading…</p>
          ) : items.length === 0 ? (
            <p className="text-[12px] text-admin-muted text-center py-10">
              No scored messages yet. Scores appear a few seconds after each chat turn.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-admin-border">
                    {['Question', 'Answer', 'F1', 'Precision', 'Recall', 'Timestamp', ''].map(h => (
                      <th
                        key={h}
                        className="px-3 py-2 text-[9px] font-semibold text-admin-muted uppercase tracking-widest"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map(item => (
                    <MessageRow key={item.message_id} item={item} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-admin-border">
              <span className="text-[11px] text-admin-muted">
                Page {page} of {pages} · {total} messages
              </span>
              <div className="flex gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))}
                  className="text-[11px] px-3 py-1 rounded border border-admin-border text-admin-muted hover:text-admin-text hover:bg-admin-hover disabled:opacity-40 transition-colors"
                >
                  ← Prev
                </button>
                <button
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(o => o + PAGE_SIZE)}
                  className="text-[11px] px-3 py-1 rounded border border-admin-border text-admin-muted hover:text-admin-text hover:bg-admin-hover disabled:opacity-40 transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
