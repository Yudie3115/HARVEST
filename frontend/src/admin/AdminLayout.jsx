import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, FileText, Search, MessageSquare,
  Settings, Plus, LogOut, Loader2, BarChart2, Library, KeyRound,
} from 'lucide-react'
import { adminApi } from './api'
import { cn } from '../lib/utils'

const NAV = [
  { to: '/admin/overview',       label: 'Overview',        Icon: LayoutDashboard },
  { to: '/admin/documents',      label: 'Documents',       Icon: FileText        },
  { to: '/admin/search',         label: 'Search',          Icon: Search          },
  { to: '/admin/qa',             label: 'Knowledge Q&A',   Icon: MessageSquare   },
  { to: '/admin/chat-quality',   label: 'Chat Quality',    Icon: BarChart2       },
  { to: '/admin/catalogue',      label: 'Q&A Catalogue',   Icon: Library         },
  { to: '/admin/access-codes',   label: 'Access Codes',    Icon: KeyRound        },
  { to: '/admin/config',         label: 'Configuration',   Icon: Settings        },
  { to: '/admin/add-document',   label: 'Add Document',    Icon: Plus            },
]

export default function AdminLayout() {
  const navigate = useNavigate()
  const [crawlLoading, setCrawlLoading] = useState(null)
  const [crawlMsg, setCrawlMsg] = useState(null)

  async function triggerCrawl(type) {
    setCrawlLoading(type)
    setCrawlMsg(null)
    try {
      await adminApi.triggerCrawl(type)
      setCrawlMsg({ type: 'ok', text: type === 'full' ? 'Full crawl triggered!' : 'Incremental update triggered!' })
    } catch (e) {
      setCrawlMsg({ type: 'err', text: e.message })
    } finally {
      setCrawlLoading(null)
      setTimeout(() => setCrawlMsg(null), 4000)
    }
  }

  function logout() {
    adminApi.logout()
    navigate('/admin/login')
  }

  return (
    <div className="flex h-screen bg-admin-bg font-admin overflow-hidden">

      {/* ── Sidebar ── */}
      <aside
        className="w-[220px] flex-shrink-0 flex flex-col border-r border-admin-border"
        style={{
          background: '#0d0d0d',
          backgroundImage: 'radial-gradient(circle, #1e1e1e 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      >
        {/* Logo */}
        <div className="px-4 py-4 border-b border-admin-border">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-admin-accent flex items-center justify-center text-sm flex-shrink-0">
              🌾
            </div>
            <div>
              <div className="text-[13px] font-semibold text-admin-text leading-tight">PostHarvest</div>
              <div className="text-[10px] text-admin-muted">Admin Panel</div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="px-3 py-3 border-b border-admin-border space-y-1.5">
          <p className="text-[9px] font-semibold text-admin-muted uppercase tracking-widest px-1 mb-2">
            Quick Actions
          </p>
          <button
            onClick={() => triggerCrawl('full')}
            disabled={crawlLoading !== null}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md bg-admin-accent text-black text-[12px] font-medium hover:bg-green-400 transition-colors disabled:opacity-50"
          >
            {crawlLoading === 'full'
              ? <Loader2 size={12} className="animate-spin" />
              : <span className="text-xs">▶</span>}
            Run Full Crawl
          </button>
          <button
            onClick={() => triggerCrawl('incremental')}
            disabled={crawlLoading !== null}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md border border-admin-border text-admin-muted text-[12px] hover:bg-admin-hover hover:text-admin-text transition-colors disabled:opacity-50"
          >
            {crawlLoading === 'incremental'
              ? <Loader2 size={12} className="animate-spin" />
              : <span className="text-xs">↻</span>}
            Incremental Update
          </button>
          {crawlMsg && (
            <p className={cn(
              'text-[11px] px-1 pt-0.5',
              crawlMsg.type === 'ok' ? 'text-admin-accent' : 'text-red-400'
            )}>
              {crawlMsg.text}
            </p>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-3 space-y-0.5 admin-scroll overflow-y-auto">
          <p className="text-[9px] font-semibold text-admin-muted uppercase tracking-widest px-2 mb-2">
            Navigation
          </p>
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 px-2.5 py-2 rounded-md text-[12px] transition-colors group',
                  isActive
                    ? 'bg-admin-active text-admin-text border-l-2 border-admin-accent pl-[calc(0.625rem-2px)]'
                    : 'text-admin-muted hover:bg-admin-hover hover:text-admin-text border-l-2 border-transparent pl-[calc(0.625rem-2px)]',
                )
              }
            >
              <Icon size={13} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-admin-border px-3 py-3 flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-[11px] font-semibold text-admin-text flex-shrink-0">
            A
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-medium text-admin-text truncate">admin</div>
            <div className="text-[10px] text-admin-muted">PostHarvest Admin</div>
          </div>
          <button
            onClick={logout}
            className="text-admin-muted hover:text-red-400 transition-colors p-1 rounded"
            title="Sign out"
          >
            <LogOut size={13} />
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 overflow-y-auto admin-scroll bg-admin-bg">
        <Outlet />
      </main>
    </div>
  )
}
