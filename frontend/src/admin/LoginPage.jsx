import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Loader2, ArrowLeft } from 'lucide-react'
import { adminApi } from './api'

export default function LoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await adminApi.login(username, password)
      navigate('/admin/overview')
    } catch (err) {
      setError(err.message || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen font-admin bg-admin-bg overflow-hidden">

      {/* ── Left branding panel ── */}
      <div
        className="hidden md:flex w-[45%] flex-col justify-between p-10 flex-shrink-0"
        style={{ background: 'linear-gradient(160deg, #052e16 0%, #071a0c 100%)' }}
      >
        <div>
          <div className="text-3xl mb-5">🌾</div>
          <h1 className="text-2xl font-semibold text-emerald-100 leading-snug mb-3">
            PostHarvest<br />Admin Panel
          </h1>
          <p className="text-sm text-emerald-400/80 leading-relaxed max-w-xs">
            AI-powered knowledge base management for post-harvest agricultural research in East Africa.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {['PostgreSQL', 'Qdrant', 'MinIO', 'Prefect', 'OpenAI'].map(s => (
            <span
              key={s}
              className="text-[11px] px-2.5 py-1 rounded border border-emerald-900 bg-emerald-950/60 text-emerald-400"
            >
              {s}
            </span>
          ))}
        </div>
      </div>

      {/* ── Right form panel ── */}
      <div className="flex-1 flex flex-col justify-center px-8 md:px-14">
        <div className="w-full max-w-sm mx-auto">

          {/* Mobile logo */}
          <div className="md:hidden text-3xl mb-6">🌾</div>

          <h2 className="text-xl font-semibold text-admin-text mb-1">Welcome back</h2>
          <p className="text-sm text-admin-muted mb-7">Enter your admin credentials to continue</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] font-medium text-admin-muted uppercase tracking-wider mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
                className="w-full rounded-md border border-admin-border bg-admin-surface px-3 py-2.5 text-sm text-admin-text placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-admin-accent focus:border-admin-accent transition-colors"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-admin-muted uppercase tracking-wider mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                className="w-full rounded-md border border-admin-border bg-admin-surface px-3 py-2.5 text-sm text-admin-text placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-admin-accent focus:border-admin-accent transition-colors"
              />
            </div>

            {error && (
              <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-md bg-admin-accent text-black font-medium text-sm py-2.5 hover:bg-green-400 transition-colors disabled:opacity-50 mt-2"
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <Link
            to="/"
            className="mt-6 flex items-center gap-1.5 text-xs text-admin-muted hover:text-admin-text transition-colors"
          >
            <ArrowLeft size={12} />
            Back to chat
          </Link>
        </div>
      </div>
    </div>
  )
}
