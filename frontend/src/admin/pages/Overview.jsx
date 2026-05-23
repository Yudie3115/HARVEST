import { useEffect, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { RefreshCw } from 'lucide-react'
import { adminApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Button } from '../../components/ui/button'

const STATUS_COLOR = {
  ok: '#22c55e',
  error: '#f43f5e',
  disabled: '#52525b',
}

function ServiceDot({ status }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ background: STATUS_COLOR[status] || '#f59e0b' }}
    />
  )
}

function StatCard({ label, value, sub, accent }) {
  return (
    <Card className="animate-fade-up">
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

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-zinc-900 border border-admin-border rounded px-3 py-2 text-xs shadow-xl">
      <p className="text-admin-muted mb-0.5">{label}</p>
      <p className="text-admin-accent font-mono font-semibold">{payload[0].value} documents</p>
    </div>
  )
}

export default function Overview() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [healthLoading, setHealthLoading] = useState(false)

  useEffect(() => {
    adminApi.getStats().then(setStats).catch(console.error)
    loadHealth()
  }, [])

  async function loadHealth() {
    setHealthLoading(true)
    try { setHealth(await adminApi.getHealth()) }
    catch (e) { console.error(e) }
    finally { setHealthLoading(false) }
  }

  const rate = stats ? `${(stats.processing_rate * 100).toFixed(1)}%` : '—'
  const pending = stats ? stats.total_documents - stats.processed_documents : null

  return (
    <div className="p-6 max-w-[1200px] font-admin">

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-admin-text">System Overview</h1>
          <p className="text-xs text-admin-muted mt-0.5">Real-time knowledge base status</p>
        </div>
        {health && (
          <div className="flex items-center gap-2 bg-admin-surface border border-admin-border rounded-md px-3 py-1.5">
            <ServiceDot status={Object.values(health).every(s => s === 'ok' || s === 'disabled') ? 'ok' : 'error'} />
            <span className="text-[11px] text-admin-muted">
              {Object.values(health).every(s => s === 'ok' || s === 'disabled') ? 'All systems operational' : 'Degraded'}
            </span>
          </div>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <StatCard
          label="Total Documents"
          value={stats ? stats.total_documents.toLocaleString() : '—'}
          sub="across all sites"
        />
        <StatCard
          label="Processed"
          value={stats ? stats.processed_documents.toLocaleString() : '—'}
          sub={pending != null ? `${pending} pending` : undefined}
        />
        <StatCard
          label="Processing Rate"
          value={rate}
          accent="#22c55e"
        />
        <StatCard
          label="Vectors Indexed"
          value={stats ? stats.vectors_count.toLocaleString() : '—'}
          sub="in Qdrant collection"
        />
      </div>

      {/* Chart + health */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-3">

        {/* Crawl activity chart */}
        <Card className="animate-fade-up" style={{ animationDelay: '60ms' }}>
          <CardHeader>
            <CardTitle>Crawl Activity</CardTitle>
            <p className="text-[11px] text-admin-muted">Documents discovered — last 30 days</p>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={stats?.crawl_activity || []} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="greenGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={d => d.slice(5)}
                />
                <YAxis
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#22c55e"
                  strokeWidth={1.5}
                  fill="url(#greenGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Service health */}
        <Card className="animate-fade-up" style={{ animationDelay: '100ms' }}>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Service Health</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={loadHealth}
              disabled={healthLoading}
              className="h-6 px-2 text-[10px]"
            >
              <RefreshCw size={10} className={healthLoading ? 'animate-spin' : ''} />
            </Button>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {health
              ? Object.entries(health).map(([name, status]) => (
                  <div key={name} className="flex items-center justify-between">
                    <span className="text-[12px] text-admin-muted">{name}</span>
                    <div className="flex items-center gap-1.5">
                      <ServiceDot status={status} />
                      <span
                        className="text-[11px] capitalize"
                        style={{ color: STATUS_COLOR[status] || '#f59e0b' }}
                      >
                        {status}
                      </span>
                    </div>
                  </div>
                ))
              : (
                <p className="text-[12px] text-admin-muted text-center py-4">
                  {healthLoading ? 'Checking…' : 'Failed to load'}
                </p>
              )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
