import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowLeft, Check, ExternalLink } from 'lucide-react'
import Header from '../../components/Header'
import { getCatalogueEntry, markCatalogueHelpful } from '../../api'
import { mdComponents } from '../../lib/markdownComponents'
import { isSafeUrl } from '../../lib/sanitize'

export default function CatalogueDetailPage() {
  const { id } = useParams()
  const [entry, setEntry] = useState(null)
  const [state, setState] = useState('loading')
  const [helpful, setHelpful] = useState(false)

  useEffect(() => {
    getCatalogueEntry(id)
      .then((result) => {
        setEntry(result)
        setState('ready')
      })
      .catch((error) => setState(error.status === 404 ? 'missing' : 'error'))
  }, [id])

  async function confirmHelpful() {
    if (helpful) return
    await markCatalogueHelpful(id)
    setHelpful(true)
  }

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#111613]">
      <Header />
      <main className="overflow-y-auto px-4 pb-16 pt-6">
        <article className="mx-auto max-w-[760px]">
          <Link to="/catalogue" className="mb-7 inline-flex items-center gap-2 text-xs text-[#8ecfaa] no-underline">
            <ArrowLeft size={14} /> Back to catalogue
          </Link>
          {state === 'loading' && <p className="text-sm text-[#8a9489]">Loading answer…</p>}
          {state === 'missing' && <h1 className="font-display text-2xl">This answer is not available.</h1>}
          {state === 'error' && <p className="text-sm text-[#d4a853]">The answer could not be loaded.</p>}
          {entry && (
            <>
              <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[#d4a853]">Reviewed answer</p>
              <h1 className="mb-7 mt-0 font-display text-[28px] font-medium leading-[1.25] text-[#e8e4da]">
                {entry.question}
              </h1>
              <div className="rounded-sm border-l-2 border-[#568164] bg-[#141a15] px-5 py-5 text-[14px] text-[#d4cfc6]">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                  {entry.answer}
                </ReactMarkdown>
              </div>
              {entry.sources?.length > 0 && (
                <section className="mt-8">
                  <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#8a9489]">Sources</h2>
                  <div className="mt-3 flex flex-col gap-2">
                    {entry.sources.filter((source) => isSafeUrl(source.url)).map((source, index) => (
                      <a
                        key={`${source.url}-${index}`}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-between gap-4 border-b border-[#263029] py-3 text-[13px] text-[#b9c4bb] no-underline hover:text-[#8ecfaa]"
                      >
                        <span>{source.title || source.site_name || 'Source document'}</span>
                        <ExternalLink size={13} />
                      </a>
                    ))}
                  </div>
                </section>
              )}
              <div className="mt-9 flex items-center justify-between gap-4 border-t border-[#2a3329] pt-5">
                <p className="m-0 text-xs text-[#7d887f]">Did this answer your question?</p>
                <button
                  onClick={confirmHelpful}
                  disabled={helpful}
                  className="inline-flex items-center gap-2 rounded-md border border-[#3d6b4f] bg-[#17251b] px-4 py-2 text-xs text-[#8ecfaa] disabled:opacity-70"
                >
                  <Check size={14} /> {helpful ? 'Feedback recorded' : 'Yes, it helped'}
                </button>
              </div>
            </>
          )}
        </article>
      </main>
    </div>
  )
}
