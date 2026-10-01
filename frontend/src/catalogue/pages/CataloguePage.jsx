import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Search } from 'lucide-react'
import Header from '../../components/Header'
import Pagination from '../../library/components/Pagination'
import { getCatalogue } from '../../api'

const LIMIT = 20

export default function CataloguePage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const offset = Number(params.get('offset') || 0)
  const [input, setInput] = useState(q)
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const pushed = useRef(q)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCatalogue({ q, offset, limit: LIMIT })
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(false)
        }
      })
      .catch(() => !cancelled && setError(true))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [q, offset])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (input === q) return
      pushed.current = input
      setParams((previous) => {
        const next = new URLSearchParams(previous)
        input ? next.set('q', input) : next.delete('q')
        next.delete('offset')
        return next
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [input, q, setParams])

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#111613]">
      <Header />
      <main className="overflow-y-auto px-4 pb-16 pt-7">
        <div className="mx-auto max-w-[780px]">
          <div className="mb-7 border-b border-[#2a3329] pb-6">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[#d4a853]">
              Reviewed field knowledge
            </p>
            <h1 className="m-0 font-display text-[28px] leading-tight text-[#e8e4da]">
              Questions, answered once and kept useful.
            </h1>
            <p className="mb-0 mt-2 max-w-[600px] text-sm leading-6 text-[#8a9489]">
              Browse practical answers drawn from trusted crop-farming sources and reviewed before publication.
            </p>
          </div>

          <label className="mb-6 flex items-center gap-3 rounded-lg border border-[#2a3329] bg-[#0f1a12] px-4 focus-within:border-[#4d7b5d]">
            <Search size={16} className="text-[#6f7c71]" />
            <span className="sr-only">Search the catalogue</span>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Search questions and answers…"
              className="w-full border-0 bg-transparent py-3 text-sm text-[#e8e4da] outline-none placeholder:text-[#59625b]"
            />
          </label>

          {error && <p className="text-sm text-[#d4a853]">The catalogue could not be loaded.</p>}
          {loading && <p className="text-sm text-[#8a9489]">Gathering reviewed answers…</p>}
          {!loading && !error && data.items.length === 0 && (
            <div className="rounded-lg border border-dashed border-[#344038] px-6 py-10 text-center">
              <p className="m-0 font-display text-lg text-[#d4cfc6]">
                {q ? 'No answers match that search.' : 'No answers have been published yet.'}
              </p>
            </div>
          )}

          {!loading && !error && (
            <div className="divide-y divide-[#263029] border-y border-[#263029]">
              {data.items.map((entry, index) => (
                <Link
                  key={entry.id}
                  to={`/catalogue/${entry.id}`}
                  className="group grid grid-cols-[32px_1fr_auto] gap-3 py-5 text-inherit no-underline transition-colors hover:bg-[#141b16]"
                >
                  <span className="pt-1 font-mono text-[10px] text-[#657067]">
                    {String(offset + index + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <h2 className="m-0 font-display text-[17px] font-medium leading-6 text-[#e8e4da]">
                      {entry.question}
                    </h2>
                    <p className="mb-0 mt-2 line-clamp-2 text-[13px] leading-5 text-[#8a9489]">
                      {entry.answer}
                    </p>
                  </div>
                  <ArrowRight size={16} className="mt-1 text-[#55705e] transition-transform group-hover:translate-x-1" />
                </Link>
              ))}
            </div>
          )}

          {data.total > LIMIT && (
            <Pagination
              offset={offset}
              limit={LIMIT}
              total={data.total}
              onChange={(value) => setParams((previous) => {
                const next = new URLSearchParams(previous)
                next.set('offset', String(value))
                return next
              })}
            />
          )}
        </div>
      </main>
    </div>
  )
}
